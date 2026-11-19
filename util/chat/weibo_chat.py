#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Weibo PC WebIM (https://api.weibo.com/chat#/chat) direct message & group chat client.

Protocol derived from REA analysis of pcweibochat (app.48f8ddda.js):
- Global AppKey: source = "209678993"
- Auth / primary info: GET /webim/query_primary_info.json
- Contact list: GET /webim/2/direct_messages/contacts.json (or public/contacts.json)
- Search contacts/groups: GET /webim/2/direct_messages/messageboxsearch.json
- Conversation history: GET /webim/2/direct_messages/conversation.json (or public/conversation.json)
- Group history: GET /webim/groupchat/query_messages.json
- Send DM: POST /webim/2/direct_messages/new.json
- Send group msg: POST /webim/groupchat/send_message.json
- Recall msg (<=3m): POST /webim/2/direct_messages/recall.json | /webim/groupchat/recall.json
- Delete msg/conv: POST /webim/2/direct_messages/destroy.json | destroy_batch.json | /webim/groupchat/delete_message.json
- Mark read: POST /webim/2/direct_messages/set_unread_count.json | /webim/groupchat/clear_unread.json
- Attachment upload: POST /webim/fileplatform/init.json -> POST /webim/uploadx.json?source=209678993&is_chunk=1
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import logging
import os

import requests
from requests.exceptions import RequestException

from util.passthrough.weibo_proxy import (
    PLACEHOLDER_COOKIES,
    WeiboPassthroughProxy,
    _default_project_root,
    _guess_mime,
    is_safe_subpath,
    normalize_weibo_image_url,
)

logger = logging.getLogger("weibo.chat")

WEBIM_BASE_URL = "https://api.weibo.com"
WEBIM_SOURCE = "209678993"
WEBIM_REFERER = "https://api.weibo.com/chat"
MAX_CHAT_IMAGE_BYTES = 25 * 1024 * 1024
DEFAULT_CHUNK_KB = 256
MAX_TRACE_ITEMS = 50


def is_group_id(target_id: str | int | None) -> bool:
    """Return True if target_id is a Weibo group chat GID (length >= 15 in pcweibochat)."""
    text = str(target_id or "").strip()
    return len(text) >= 15 and text.isdigit()


def _format_epoch_time(val) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, (int, float)):
        ts = float(val)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(val)
    text = str(val).strip()
    if text.isdigit():
        num = int(text)
        ts = num / 1000.0 if num > 10**12 else float(num)
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return text
    return text


def _to_webim_subpath(path: str) -> str:
    """Normalize ``/webim/2/x.json`` / ``webim/2/x.json`` / ``2/x.json`` to ``2/x.json``."""
    sub = str(path or "").strip()
    if sub.startswith("/"):
        sub = sub[1:]
    if sub.startswith("webim/"):
        sub = sub[len("webim/"):]
    return sub


class WeiboChatClient:
    """Weibo PC WebIM direct message & group chat client built on the Mode 1 pass-through.

    Every request is sent through the native ``/webim/<subpath>`` pass-through interface
    (``WeiboPassthroughProxy.proxy_webim``), which owns Cookie injection, ``source``/``t``
    parameters, ``Referer``/``Origin`` headers and ``error_code == 21301`` refresh-retry.

    Two transports are supported:

    - **in-process** (default): calls ``proxy.proxy_webim(...)`` directly (shared proxy in
      ``service.py`` or a private proxy built from ``project_root``).
    - **http**: when ``passthrough_base_url`` is given (e.g. ``http://127.0.0.1:15001``),
      calls the running service's ``{base}/webim/<subpath>`` endpoint over HTTP.
    """

    def __init__(
        self,
        cookie: str | None = None,
        project_root: str | None = None,
        session: requests.Session | None = None,
        auto_refresh: bool = True,
        timeout: int = 15,
        proxy: WeiboPassthroughProxy | None = None,
        passthrough_base_url: str | None = None,
    ):
        self.project_root = os.path.abspath(project_root or _default_project_root())
        self.timeout = timeout
        self.auto_refresh = auto_refresh
        self.cookie_str = str(cookie).strip() if cookie else ""
        self.passthrough_base_url = (
            str(passthrough_base_url).rstrip("/") if passthrough_base_url else ""
        )

        if self.passthrough_base_url:
            self.transport = "http"
            self.proxy = None
            self.http_session = session or requests.Session()
        else:
            self.transport = "in-process"
            self.http_session = None
            self.proxy = proxy or WeiboPassthroughProxy(
                project_root=self.project_root,
                session=session,
                auto_refresh=auto_refresh,
                timeout=max(int(timeout), 15),
            )

        self.trace: list[dict] = []
        self._uid: str = ""
        self._screen_name: str = ""
        self._avatar: str = ""

    # ------------------------------------------------------------------
    # Mode 1 pass-through transport
    # ------------------------------------------------------------------
    def _caller_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.cookie_str and self.cookie_str not in PLACEHOLDER_COOKIES:
            headers["X-Weibo-Cookie"] = self.cookie_str
        return headers

    def _ensure_cookie_present(self) -> bool:
        if self.transport == "http":
            return True
        if self.cookie_str and self.cookie_str not in PLACEHOLDER_COOKIES:
            return True
        proxy = self.proxy
        reload_fn = getattr(proxy, "_reload_project_cookie_if_needed", None)
        if callable(reload_fn):
            try:
                reload_fn()
            except Exception:
                pass
        current = str(getattr(proxy, "_cookie_str", "") or "")
        if current and current not in PLACEHOLDER_COOKIES:
            return True
        refresh_fn = getattr(proxy, "_try_browser_refresh", None)
        if self.auto_refresh and callable(refresh_fn):
            try:
                return bool(refresh_fn(prefer_domain="weibo.com"))
            except Exception:
                return False
        return False

    def _record_trace(self, method: str, subpath: str, status: int, upstream: str) -> None:
        self.trace.append(
            {
                "method": method,
                "path": f"/webim/{subpath}",
                "status": int(status),
                "upstream": upstream or f"{WEBIM_BASE_URL}/webim/{subpath}",
                "transport": self.transport,
            }
        )
        if len(self.trace) > MAX_TRACE_ITEMS:
            self.trace = self.trace[-MAX_TRACE_ITEMS:]

    def call_passthrough(
        self,
        method: str,
        path: str,
        params: dict | list | None = None,
        form_data: dict | None = None,
        files: dict | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Send one raw request through the ``/webim/<subpath>`` pass-through interface."""
        subpath = _to_webim_subpath(path)
        method_u = str(method or "GET").upper()
        if not is_safe_subpath(subpath):
            body = json.dumps({"ok": 0, "msg": f"非法 WebIM 路径: {path!r}"}, ensure_ascii=False)
            return 400, {"Content-Type": "application/json"}, body.encode("utf-8")

        form = None
        if form_data is not None:
            form = {
                k: v for k, v in form_data.items() if v is not None and v != ""
            }

        if self.transport == "http":
            url = f"{self.passthrough_base_url}/webim/{subpath}"
            req_kwargs: dict = {
                "params": params or None,
                "headers": self._caller_headers(),
                "timeout": max(self.timeout, 60) if files else self.timeout,
            }
            if method_u != "GET":
                if files:
                    req_kwargs["files"] = files
                    req_kwargs["data"] = form or {}
                else:
                    req_kwargs["data"] = form or {}
            try:
                resp = self.http_session.request(method_u, url, **req_kwargs)
            except RequestException as exc:
                body = json.dumps(
                    {"ok": 0, "msg": f"连接本地透传服务失败 ({url}): {exc}"},
                    ensure_ascii=False,
                )
                self._record_trace(method_u, subpath, 502, url)
                return 502, {"Content-Type": "application/json"}, body.encode("utf-8")
            status = int(getattr(resp, "status_code", 200))
            headers = dict(getattr(resp, "headers", {}) or {})
            content = getattr(resp, "content", b"") or b""
            if isinstance(content, str):
                content = content.encode("utf-8")
            upstream = headers.get("X-Weibo-Passthrough-Upstream", "")
            self._record_trace(method_u, subpath, status, upstream)
            return status, headers, content

        status, headers, content = self.proxy.proxy_webim(
            subpath,
            method=method_u,
            query_params=params,
            headers=self._caller_headers(),
            form_data=form if method_u != "GET" else None,
            files=files if method_u != "GET" else None,
        )
        self._record_trace(
            method_u, subpath, status, (headers or {}).get("X-Weibo-Passthrough-Upstream", "")
        )
        return status, headers, content

    @staticmethod
    def _is_auth_error(js: dict | list | None, status_code: int) -> bool:
        if status_code in (401, 403, 432):
            return True
        if isinstance(js, dict):
            if js.get("error_code") == 21301 or js.get("ok") == -100:
                return True
            err_text = str(js.get("error") or "").lower()
            if "sub invalid" in err_text:
                return True
        return False

    def _interpret(
        self, path: str, status: int, content: bytes
    ) -> tuple[bool, dict | list | None, str]:
        try:
            js = json.loads((content or b"").decode("utf-8")) if content else None
        except (ValueError, UnicodeDecodeError):
            return False, None, f"接口 {path} 返回非 JSON 响应 (HTTP {status})"

        if self._is_auth_error(js, status):
            msg = (js.get("error") if isinstance(js, dict) else "") or "私信 WebIM 登录态已过期，请更新 Cookie"
            return False, js, str(msg)

        if isinstance(js, dict):
            if js.get("error") or js.get("error_code"):
                return False, js, str(js.get("error") or f"WebIM 错误 ({js.get('error_code')})")
            if js.get("ok") == 0 and js.get("msg") and status >= 400:
                return False, js, str(js["msg"])
        if status >= 400:
            return False, js, f"接口 {path} 请求失败 (HTTP {status})"
        return True, js, ""

    def _get_webim(
        self, path: str, params: dict | None = None
    ) -> tuple[bool, dict | list | None, str]:
        if not self._ensure_cookie_present():
            return False, None, "未配置有效微博 Cookie，请先在设置页填入或一键从浏览器提取"
        status, _, content = self.call_passthrough("GET", path, params=params)
        return self._interpret(path, status, content)

    def _post_webim(
        self,
        path: str,
        form_data: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
    ) -> tuple[bool, dict | list | None, str]:
        if not self._ensure_cookie_present():
            return False, None, "未配置有效微博 Cookie，请先在设置页填入或一键从浏览器提取"
        status, _, content = self.call_passthrough(
            "POST", path, params=params, form_data=dict(form_data or {}), files=files
        )
        return self._interpret(path, status, content)

    def raw_request(
        self,
        method: str,
        path: str,
        params: dict | list | None = None,
        form_data: dict | None = None,
        files: dict | None = None,
    ) -> dict:
        """Call any native ``/webim/*`` endpoint via the pass-through and return parsed JSON."""
        status, headers, content = self.call_passthrough(
            method, path, params=params, form_data=form_data, files=files
        )
        try:
            data = json.loads(content.decode("utf-8")) if content else None
        except (ValueError, UnicodeDecodeError):
            data = (content or b"").decode("utf-8", errors="replace")
        ok, _, err = self._interpret(path, status, content)
        return {
            "ok": ok,
            "status": status,
            "path": f"/webim/{_to_webim_subpath(path)}",
            "upstream": (headers or {}).get("X-Weibo-Passthrough-Upstream", ""),
            "data": data,
            "message": err or "OK",
            "msg": err or "OK",
        }

    def check_auth(self, force: bool = False) -> dict:
        """Verify WebIM personal login state via /webim/query_primary_info.json."""
        if self._uid and not force:
            return {
                "ok": True,
                "logged_in": True,
                "authenticated": True,
                "uid": self._uid,
                "screen_name": self._screen_name,
                "avatar": self._avatar,
                "avatar_hd": self._avatar,
                "message": f"私信登录态有效（账号：{self._screen_name or self._uid}）",
            }

        ok, js, err = self._get_webim("/webim/query_primary_info.json")
        if not ok or not isinstance(js, dict):
            return {
                "ok": False,
                "logged_in": False,
                "authenticated": False,
                "uid": "",
                "screen_name": "",
                "avatar": "",
                "avatar_hd": "",
                "message": err or "私信登录态校验未通过",
                "raw": js,
            }

        profile = js.get("profile") if isinstance(js.get("profile"), dict) else {}
        uid = str(profile.get("id") or js.get("uid") or "")
        screen_name = str(profile.get("screen_name") or profile.get("name") or "")
        avatar = normalize_weibo_image_url(
            profile.get("profileImageUrl")
            or profile.get("avatar_large")
            or profile.get("profile_image_url")
            or ""
        )
        if not uid:
            return {
                "ok": False,
                "logged_in": False,
                "authenticated": False,
                "uid": "",
                "screen_name": "",
                "avatar": "",
                "avatar_hd": "",
                "message": "未能获取到私信登录账号信息（请确认不是匿名访客 Cookie）",
                "raw": js,
            }

        self._uid = uid
        self._screen_name = screen_name
        self._avatar = avatar
        display = screen_name or f"UID:{uid}"
        return {
            "ok": True,
            "logged_in": True,
            "authenticated": True,
            "uid": uid,
            "screen_name": screen_name,
            "avatar": avatar,
            "avatar_hd": avatar,
            "websocket_gray": bool(js.get("websocket_gray")),
            "message": f"私信登录态有效（账号：{display}）",
            "raw": js,
        }

    def list_contacts(
        self,
        count: int = 50,
        cursor: int = 0,
        is_include_group: int = 1,
        include_group: bool | int | None = None,
        is_include_folder: int = 0,
        unfollow: bool = False,
        filter_msg_type: int | None = None,
    ) -> dict:
        """Fetch recent direct message contacts / conversations."""
        inc_group = (
            bool(include_group)
            if include_group is not None
            else bool(is_include_group)
        )
        if unfollow:
            params: dict = {"count": int(count), "cursor": int(cursor)}
            if filter_msg_type is not None:
                params["filter_msg_type"] = int(filter_msg_type)
            ok, js, err = self._get_webim(
                "/webim/2/direct_messages/public/contacts.json", params=params
            )
        else:
            params = {
                "special_source": 3,
                "add_virtual_user": "3,4",
                "is_include_group": 1 if inc_group else 0,
                "need_back": "0,0",
                "is_include_folder": 1 if is_include_folder else 0,
                "count": int(count),
                "cursor": int(cursor),
            }
            ok, js, err = self._get_webim(
                "/webim/2/direct_messages/contacts.json", params=params
            )

        if not ok or not isinstance(js, dict):
            msg_err = err or "获取私信联系人列表失败"
            return {
                "ok": False,
                "items": [],
                "contacts": [],
                "msg": msg_err,
                "message": msg_err,
                "raw": js,
            }

        raw_contacts = js.get("contacts") if isinstance(js.get("contacts"), list) else []
        items = []
        for entry in raw_contacts:
            if not isinstance(entry, dict):
                continue
            user = entry.get("user") if isinstance(entry.get("user"), dict) else {}
            msg = entry.get("message") if isinstance(entry.get("message"), dict) else {}
            cid = str(user.get("id") or entry.get("id") or "")
            if not cid:
                continue
            user_type = int(user.get("type") or entry.get("type") or 1)
            group_flag = user_type == 2 or is_group_id(cid)
            last_text = str(msg.get("text") or msg.get("content") or "")
            last_time = _format_epoch_time(msg.get("created_at") or msg.get("time"))
            items.append(
                {
                    "id": cid,
                    "name": str(user.get("screen_name") or user.get("name") or cid),
                    "avatar": normalize_weibo_image_url(
                        user.get("avatar_large")
                        or user.get("profile_image_url")
                        or user.get("round_avatar_large")
                        or ""
                    ),
                    "type": user_type,
                    "is_group": group_flag,
                    "unread_count": int(entry.get("unread_count") or 0),
                    "is_top": bool(entry.get("is_top_user")),
                    "is_blocked": bool(entry.get("is_blocked")),
                    "last_text": last_text,
                    "last_time": last_time,
                    "last_message": {
                        "mid": str(msg.get("idstr") or msg.get("id") or msg.get("mid") or ""),
                        "text": last_text,
                        "created_at": last_time,
                        "sender_id": str(msg.get("sender_id") or msg.get("from_uid") or ""),
                    },
                }
            )

        return {
            "ok": True,
            "items": items,
            "contacts": items,
            "total": len(items),
            "unfollow": bool(unfollow),
            "msg": f"获取到 {len(items)} 个会话",
            "message": f"获取到 {len(items)} 个会话",
            "raw": js,
        }

    def search_contacts(
        self, keyword: str, pagecount: int = 20, count: int | None = None
    ) -> dict:
        """Search DM contacts and groups via /webim/2/direct_messages/messageboxsearch.json."""
        kw = str(keyword or "").strip()
        if not kw:
            return {
                "ok": False,
                "items": [],
                "contacts": [],
                "msg": "搜索关键词不能为空",
                "message": "搜索关键词不能为空",
            }

        limit = int(count) if count is not None else int(pagecount)
        ok, js, err = self._get_webim(
            "/webim/2/direct_messages/messageboxsearch.json",
            params={"types": "contact,group", "key": kw, "pagecount": limit},
        )
        if not ok or not isinstance(js, dict):
            msg_err = err or "搜索私信联系人失败"
            return {
                "ok": False,
                "items": [],
                "contacts": [],
                "msg": msg_err,
                "message": msg_err,
                "raw": js,
            }

        root = js.get("result") if isinstance(js.get("result"), dict) else js
        items = []
        contacts_block = (
            root.get("contacts") if isinstance(root.get("contacts"), dict) else {}
        )
        contact_candidates = (
            contacts_block.get("contact_result_list")
            or contacts_block.get("users")
            or []
        )
        for c in contact_candidates:
            if isinstance(c, dict) and c.get("id"):
                desc = str(c.get("description") or "")
                items.append(
                    {
                        "id": str(c["id"]),
                        "name": str(c.get("screen_name") or c.get("name") or c["id"]),
                        "avatar": normalize_weibo_image_url(
                            c.get("avatar_large") or c.get("profile_image_url") or ""
                        ),
                        "type": 1,
                        "is_group": False,
                        "unread_count": 0,
                        "last_text": desc,
                        "last_message": {"mid": "", "text": desc, "created_at": ""},
                    }
                )

        groups_block = root.get("groups") if isinstance(root.get("groups"), dict) else {}
        group_candidates = (
            (groups_block.get("group_result_list") or [])
            + (groups_block.get("group_member_result_list") or [])
            + (groups_block.get("groups") or [])
        )
        for g in group_candidates:
            if isinstance(g, dict) and (g.get("id") or g.get("gid")):
                gid = str(g.get("id") or g.get("gid"))
                items.append(
                    {
                        "id": gid,
                        "name": str(g.get("name") or g.get("screen_name") or gid),
                        "avatar": normalize_weibo_image_url(
                            g.get("avatar_large") or g.get("round_avatar") or ""
                        ),
                        "type": 2,
                        "is_group": True,
                        "unread_count": 0,
                        "last_text": "群聊",
                        "last_message": {"mid": "", "text": "群聊", "created_at": ""},
                    }
                )

        return {
            "ok": True,
            "items": items,
            "contacts": items,
            "total": len(items),
            "msg": f"搜索到 {len(items)} 个结果",
            "message": f"搜索到 {len(items)} 个结果",
            "raw": js,
        }

    def get_conversation(
        self,
        uid: str | int,
        count: int = 15,
        max_id: int | str = 0,
        unfollow: bool = False,
        folder_id: str | int | None = None,
    ) -> dict:
        """Fetch 1-on-1 direct message history with ``uid``."""
        target_uid = str(uid or "").strip()
        if not target_uid:
            return {
                "ok": False,
                "items": [],
                "messages": [],
                "msg": "缺少对方用户 uid",
                "message": "缺少对方用户 uid",
            }

        endpoint = (
            "/webim/2/direct_messages/public/conversation.json"
            if unfollow
            else "/webim/2/direct_messages/conversation.json"
        )
        params: dict = {
            "convert_emoji": 1,
            "count": int(count),
            "max_id": max_id,
            "uid": target_uid,
            "is_include_group": 0,
        }
        if folder_id is not None and folder_id != "":
            params["folder_id"] = folder_id

        ok, js, err = self._get_webim(endpoint, params=params)
        if not ok or not isinstance(js, dict):
            msg_err = err or "获取单聊私信记录失败"
            return {
                "ok": False,
                "target_id": target_uid,
                "is_group": False,
                "items": [],
                "messages": [],
                "msg": msg_err,
                "message": msg_err,
                "raw": js,
            }

        dms = js.get("direct_messages") if isinstance(js.get("direct_messages"), list) else []
        items = []
        for m in dms:
            if not isinstance(m, dict):
                continue
            sender = m.get("sender") if isinstance(m.get("sender"), dict) else {}
            recipient = m.get("recipient") if isinstance(m.get("recipient"), dict) else {}
            mid = str(m.get("idstr") or m.get("id") or m.get("mid") or "")
            sender_id = str(m.get("sender_id") or sender.get("id") or "")
            recipient_id = str(m.get("recipient_id") or recipient.get("id") or "")
            items.append(
                {
                    "mid": mid,
                    "text": str(m.get("text") or m.get("content") or ""),
                    "created_at": _format_epoch_time(m.get("created_at") or m.get("time")),
                    "sender_id": sender_id,
                    "sender_uid": sender_id,
                    "sender_name": str(
                        m.get("sender_screen_name")
                        or sender.get("screen_name")
                        or sender.get("name")
                        or ""
                    ),
                    "recipient_id": recipient_id,
                    "recipient_uid": recipient_id,
                    "recipient_name": str(
                        m.get("recipient_screen_name")
                        or recipient.get("screen_name")
                        or ""
                    ),
                    "media_type": int(m.get("media_type") or 0),
                    "fids": m.get("att_ids") or m.get("fids") or [],
                    "is_large_dm": bool(m.get("isLargeDm")),
                }
            )

        return {
            "ok": True,
            "target_id": target_uid,
            "is_group": False,
            "items": items,
            "messages": items,
            "total_number": js.get("total_number", len(items)),
            "msg": f"获取到 {len(items)} 条私信",
            "message": f"获取到 {len(items)} 条私信",
            "raw": js,
        }

    def get_group_messages(
        self, gid: str | int, count: int = 20, max_mid: int | str = 0
    ) -> dict:
        """Fetch group chat history via /webim/groupchat/query_messages.json."""
        target_gid = str(gid or "").strip()
        if not target_gid:
            return {
                "ok": False,
                "items": [],
                "messages": [],
                "msg": "缺少群聊 gid",
                "message": "缺少群聊 gid",
            }

        ok, js, err = self._get_webim(
            "/webim/groupchat/query_messages.json",
            params={
                "convert_emoji": 1,
                "query_sender": 1,
                "count": int(count),
                "id": target_gid,
                "max_mid": max_mid,
            },
        )
        if not ok or not isinstance(js, dict):
            msg_err = err or "获取群聊消息记录失败"
            return {
                "ok": False,
                "target_id": target_gid,
                "is_group": True,
                "items": [],
                "messages": [],
                "msg": msg_err,
                "message": msg_err,
                "raw": js,
            }

        msgs = js.get("messages") if isinstance(js.get("messages"), list) else []
        items = []
        for m in msgs:
            if not isinstance(m, dict):
                continue
            from_user = (
                m.get("from_user")
                if isinstance(m.get("from_user"), dict)
                else (
                    m.get("sender_info")
                    if isinstance(m.get("sender_info"), dict)
                    else {}
                )
            )
            mid = str(m.get("id") or m.get("mid") or "")
            sender_id = str(m.get("from_uid") or from_user.get("id") or "")
            items.append(
                {
                    "mid": mid,
                    "text": str(m.get("content") or m.get("text") or ""),
                    "created_at": _format_epoch_time(m.get("time") or m.get("created_at")),
                    "sender_id": sender_id,
                    "sender_uid": sender_id,
                    "sender_name": str(
                        from_user.get("screen_name")
                        or from_user.get("name")
                        or m.get("from_uid")
                        or ""
                    ),
                    "recipient_id": target_gid,
                    "recipient_uid": target_gid,
                    "media_type": int(m.get("media_type") or m.get("type") or 0),
                    "fids": m.get("fids") or [],
                }
            )

        return {
            "ok": True,
            "target_id": target_gid,
            "is_group": True,
            "items": items,
            "messages": items,
            "total_number": len(items),
            "msg": f"获取到 {len(items)} 条群消息",
            "message": f"获取到 {len(items)} 条群消息",
            "raw": js,
        }

    def get_full_message(
        self, dmid: str | int, gid: str | int | None = None
    ) -> dict:
        """Fetch full text of an oversized DM or single group message."""
        mid_str = str(dmid or "").strip()
        if not mid_str:
            return {"ok": False, "msg": "缺少消息 mid"}
        if gid:
            ok, js, err = self._get_webim(
                "/webim/groupchat/query_message.json",
                params={"id": str(gid), "mid": mid_str},
            )
            if not ok or not isinstance(js, dict):
                return {"ok": False, "msg": err or "获取群消息详情失败", "raw": js}
            msg_obj = js.get("message") if isinstance(js.get("message"), dict) else {}
            return {
                "ok": True,
                "mid": mid_str,
                "text": str(msg_obj.get("content") or msg_obj.get("text") or ""),
                "raw": js,
            }

        ok, js, err = self._get_webim(
            "/webim/2/direct_messages/show_batch.json",
            params={"is_complete": 1, "is_encoded": 0, "dmids": mid_str},
        )
        if not ok:
            return {"ok": False, "msg": err or "获取长私信详情失败", "raw": js}
        first = js[0] if isinstance(js, list) and js and isinstance(js[0], dict) else (js if isinstance(js, dict) else {})
        return {
            "ok": True,
            "mid": mid_str,
            "text": str(first.get("text") or first.get("content") or ""),
            "raw": js,
        }

    def upload_attachment(
        self,
        recipient_id: str | int,
        file_path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        is_group: bool | None = None,
        unfollow: bool = False,
    ) -> dict:
        """Upload an image or file attachment for Weibo chat and return ``fid``."""
        target = str(recipient_id or "").strip()
        if not target:
            return {"ok": False, "msg": "上传私信附件缺少接收方 uid 或 gid"}

        if data is None:
            if not file_path or not os.path.isfile(file_path):
                return {"ok": False, "msg": f"附件文件不存在: {file_path}"}
            with open(file_path, "rb") as f:
                raw = f.read()
            resolved_name = filename or os.path.basename(file_path)
        else:
            raw = bytes(data)
            resolved_name = filename or "image.jpg"

        if not raw:
            return {"ok": False, "msg": f"附件文件大小不能为 0: {resolved_name}"}

        is_pic = resolved_name.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        ) or str(mime_type or "").lower().startswith("image/")
        if is_pic and len(raw) > MAX_CHAT_IMAGE_BYTES:
            return {"ok": False, "msg": f"私信图片不能超过 25MB: {resolved_name}"}

        resolved_mime = mime_type or (_guess_mime(resolved_name) if is_pic else "application/octet-stream")
        group_flag = is_group_id(target) if is_group is None else bool(is_group)
        upload_type = 3 if group_flag else (2 if unfollow else 1)
        att_type = "dm_attachment_pic" if is_pic else "dm_attachment_default"
        md5_hex = hashlib.md5(raw).hexdigest()

        init_form = {
            "extprops": json.dumps(
                {"uploadType": upload_type, "recipientId": target},
                ensure_ascii=False,
            ),
            "length": len(raw),
            "name": resolved_name,
            "type": att_type,
            "md5": md5_hex,
            "check": md5_hex,
        }
        ok_init, init_js, init_err = self._post_webim(
            "/webim/fileplatform/init.json", form_data=init_form
        )
        file_token = (
            str(init_js.get("fileToken") or "")
            if ok_init and isinstance(init_js, dict)
            else ""
        )

        if file_token:
            chunk_kb = int((init_js or {}).get("length") or DEFAULT_CHUNK_KB)
            chunk_bytes = max(1024, chunk_kb * 1024)
            last_js: dict = {}
            offset = 0
            while offset < len(raw):
                piece = raw[offset : offset + chunk_bytes]
                up_form = {
                    "source": WEBIM_SOURCE,
                    "filetoken": file_token,
                    "startloc": offset,
                    "filelength": len(raw),
                    "filecheck": md5_hex,
                    "selectId": target,
                }
                ok_up, up_js, up_err = self._post_webim(
                    "/webim/uploadx.json",
                    form_data=up_form,
                    params={"source": WEBIM_SOURCE, "is_chunk": 1},
                    files={"file": (resolved_name, piece, resolved_mime)},
                )
                if not ok_up:
                    return {
                        "ok": False,
                        "msg": up_err or "分片上传私信附件失败",
                        "raw": up_js,
                    }
                if isinstance(up_js, dict):
                    last_js = up_js
                offset += len(piece)

            fid = str(last_js.get("fid") or (init_js or {}).get("fid") or "")
            if fid:
                return {
                    "ok": True,
                    "fid": fid,
                    "file_token": file_token,
                    "media_type": 1 if is_pic else 5,
                    "filename": resolved_name,
                    "raw": last_js,
                }

        # Fallback: single-shot uploadx.json with imageName (used by pcweibochat for screenshots/images)
        if is_pic:
            q_params = {
                "source": WEBIM_SOURCE,
                "gid" if group_flag else "uid": target,
            }
            ok_fb, fb_js, fb_err = self._post_webim(
                "/webim/uploadx.json",
                params=q_params,
                files={"imageName": (resolved_name, raw, resolved_mime)},
            )
            if ok_fb and isinstance(fb_js, dict) and fb_js.get("fid"):
                return {
                    "ok": True,
                    "fid": str(fb_js["fid"]),
                    "media_type": 1,
                    "filename": resolved_name,
                    "thumbnail": fb_js.get("thumbnail_600") or "",
                    "raw": fb_js,
                }
            return {
                "ok": False,
                "msg": fb_err or init_err or "上传私信图片失败",
                "raw": fb_js or init_js,
            }

        return {
            "ok": False,
            "msg": init_err or "初始化私信附件上传失败",
            "raw": init_js,
        }

    def send_message(
        self,
        uid: str | int | None = None,
        gid: str | int | None = None,
        text: str = "",
        file_path: str | None = None,
        data: bytes | None = None,
        file_bytes: bytes | None = None,
        filename: str | None = None,
        fid: str | None = None,
        media_type: int | None = None,
        client_id: str = "",
        at_all: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Send a 1-on-1 direct message or group chat message."""
        if data is None and file_bytes is not None:
            data = file_bytes
        if gid is not None and str(gid).strip():
            target_id = str(gid).strip()
            group_flag = True
        elif uid is not None and str(uid).strip():
            target_id = str(uid).strip()
            group_flag = is_group_id(target_id)
        else:
            return {"ok": False, "msg": "请提供接收方 uid 或群聊 gid", "message": "请提供接收方 uid 或群聊 gid"}

        msg_text = str(text or "")
        resolved_fid = str(fid or "").strip()
        resolved_media_type = media_type

        if not msg_text.strip() and not resolved_fid and not file_path and data is None:
            return {
                "ok": False,
                "msg": "私信内容与附件不能同时为空",
                "message": "私信内容与附件不能同时为空",
            }

        if (file_path or data is not None) and not resolved_fid:
            if dry_run:
                resolved_fid = "dry_run_fid"
                resolved_media_type = resolved_media_type or 1
                if not msg_text.strip():
                    msg_text = "分享图片" if resolved_media_type == 1 else (filename or "分享文件")
            else:
                up_res = self.upload_attachment(
                    target_id,
                    file_path=file_path,
                    data=data,
                    filename=filename,
                    is_group=group_flag,
                )
                if not up_res.get("ok"):
                    if "message" not in up_res:
                        up_res["message"] = up_res.get("msg", "")
                    return up_res
                resolved_fid = str(up_res["fid"])
                resolved_media_type = resolved_media_type or int(up_res.get("media_type") or 1)
                if not msg_text.strip():
                    msg_text = (
                        "分享图片"
                        if resolved_media_type == 1
                        else (up_res.get("filename") or "分享文件")
                    )

        if group_flag:
            endpoint = "/webim/groupchat/send_message.json"
            form: dict = {
                "id": target_id,
                "content": msg_text or "分享图片",
                "annotations": json.dumps(
                    {"webchat": 1, "clientid": client_id}, ensure_ascii=False
                ),
                "return_detail": 1,
                "is_encoded": 0,
                "source": WEBIM_SOURCE,
            }
            if resolved_fid:
                form["fids"] = resolved_fid
                form["media_type"] = int(resolved_media_type or 1)
            if at_all:
                form["at_all"] = 1
        else:
            endpoint = "/webim/2/direct_messages/new.json"
            form = {
                "uid": target_id,
                "text": msg_text or "分享图片",
                "extensions": json.dumps({"clientid": client_id}, ensure_ascii=False),
                "is_encoded": 0,
                "decodetime": 1,
                "source": WEBIM_SOURCE,
            }
            if resolved_fid:
                form["fids"] = resolved_fid
                form["media_type"] = int(resolved_media_type or 1)

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "is_group": group_flag,
                "target_id": target_id,
                "endpoint": endpoint,
                "payload": form,
                "fid": resolved_fid,
                "fids": resolved_fid,
                "msg": "私信干跑校验通过（未实际发送）",
                "message": "私信干跑校验通过（未实际发送）",
            }

        ok, js, err = self._post_webim(endpoint, form_data=form)
        if not ok or not isinstance(js, dict):
            msg_err = err or "发送私信失败"
            return {
                "ok": False,
                "is_group": group_flag,
                "target_id": target_id,
                "msg": msg_err,
                "message": msg_err,
                "raw": js,
            }

        mid = str(js.get("mid") or js.get("idstr") or js.get("id") or "")
        return {
            "ok": True,
            "is_group": group_flag,
            "target_id": target_id,
            "mid": mid,
            "text": str(js.get("content") or js.get("text") or msg_text),
            "created_at": _format_epoch_time(js.get("created_at") or js.get("time")),
            "fid": resolved_fid,
            "fids": resolved_fid,
            "msg": "发送成功",
            "message": "发送成功",
            "raw": js,
        }

    def recall_message(
        self, mid: str | int, gid: str | int | None = None
    ) -> dict:
        """Recall a sent DM or group message (within 3 minutes)."""
        mid_str = str(mid or "").strip()
        if not mid_str:
            return {"ok": False, "msg": "缺少需要撤回的消息 mid", "message": "缺少需要撤回的消息 mid"}

        if gid is not None and str(gid).strip():
            gid_str = str(gid).strip()
            ok, js, err = self._post_webim(
                "/webim/groupchat/recall.json",
                form_data={"gid": gid_str, "mid": mid_str},
            )
        else:
            ok, js, err = self._post_webim(
                "/webim/2/direct_messages/recall.json",
                form_data={"id": mid_str},
            )

        if not ok:
            if "三分钟" in str(err) or "3 mins" in str(err):
                err = "无法撤回超过 3 分钟的消息"
            msg_err = err or "撤回消息失败"
            return {"ok": False, "mid": mid_str, "msg": msg_err, "message": msg_err, "raw": js}

        return {"ok": True, "mid": mid_str, "msg": "消息已撤回", "message": "消息已撤回", "raw": js}

    def delete_message(
        self,
        mid: str | int | None = None,
        uid: str | int | None = None,
        gid: str | int | None = None,
        unfollow: bool = False,
    ) -> dict:
        """Delete a single DM/group message or an entire conversation."""
        mid_str = str(mid or "").strip()
        uid_str = str(uid or "").strip()
        gid_str = str(gid or "").strip()

        if gid_str:
            form = (
                {"id": gid_str, "mid": mid_str}
                if mid_str
                else {"id": gid_str, "keep_entrance": 0}
            )
            ok, js, err = self._post_webim(
                "/webim/groupchat/delete_message.json", form_data=form
            )
            if not ok:
                msg_err = err or "删除群消息失败"
                return {"ok": False, "msg": msg_err, "message": msg_err, "raw": js}
            return {"ok": True, "gid": gid_str, "mid": mid_str, "msg": "删除成功", "message": "删除成功", "raw": js}

        if uid_str or (mid_str and unfollow):
            endpoint = (
                "/webim/2/direct_messages/public/destroy_batch.json"
                if unfollow
                else "/webim/2/direct_messages/destroy_batch.json"
            )
            form = {"uid": uid_str} if uid_str else {"ids": mid_str}
            ok, js, err = self._post_webim(endpoint, form_data=form)
            if not ok:
                msg_err = err or "批量删除私信失败"
                return {"ok": False, "msg": msg_err, "message": msg_err, "raw": js}
            return {"ok": True, "uid": uid_str, "mid": mid_str, "msg": "删除成功", "message": "删除成功", "raw": js}

        if mid_str:
            ok, js, err = self._post_webim(
                "/webim/2/direct_messages/destroy.json", form_data={"id": mid_str}
            )
            if not ok:
                msg_err = err or "删除私信失败"
                return {"ok": False, "msg": msg_err, "message": msg_err, "raw": js}
            return {"ok": True, "mid": mid_str, "msg": "删除成功", "message": "删除成功", "raw": js}

        return {"ok": False, "msg": "请提供 mid、uid 或 gid", "message": "请提供 mid、uid 或 gid"}

    def mark_read(
        self,
        uid: str | int | None = None,
        gid: str | int | None = None,
        unfollow: bool = False,
        is_folder: bool = False,
    ) -> dict:
        """Clear unread badge for a single conversation, group chat, or unfollow box."""
        gid_str = str(gid or "").strip()
        uid_str = str(uid or "").strip()

        if gid_str or (uid_str and is_group_id(uid_str)):
            target_gid = gid_str or uid_str
            ok, js, err = self._post_webim(
                "/webim/groupchat/clear_unread.json", form_data={"id": target_gid}
            )
            if not ok:
                msg_err = err or "清除群聊未读数失败"
                return {"ok": False, "msg": msg_err, "message": msg_err, "raw": js}
            return {"ok": True, "target_id": target_gid, "msg": "已标记为已读", "message": "已标记为已读", "raw": js}

        if uid_str:
            endpoint = (
                "/webim/2/direct_messages/public/set_unread_count.json"
                if unfollow
                else "/webim/2/direct_messages/set_unread_count.json"
            )
            form = (
                {"uid": uid_str, "type": 2, "is_folder": 1}
                if is_folder
                else {"uid": uid_str, "type": 2, "is_include_group": 0}
            )
            ok, js, err = self._post_webim(endpoint, form_data=form)
            if not ok:
                msg_err = err or "清除单聊未读数失败"
                return {"ok": False, "msg": msg_err, "message": msg_err, "raw": js}
            return {"ok": True, "target_id": uid_str, "msg": "已标记为已读", "message": "已标记为已读", "raw": js}

        if unfollow:
            ok, js, err = self._post_webim(
                "/webim/2/direct_messages/public/reset_unread_count.json"
            )
            if not ok:
                msg_err = err or "重置未关注人未读数失败"
                return {"ok": False, "msg": msg_err, "message": msg_err, "raw": js}
            return {"ok": True, "msg": "已清空未关注人未读数", "message": "已清空未关注人未读数", "raw": js}

        return {"ok": False, "msg": "请提供 uid、gid 或设置 unfollow=True", "message": "请提供 uid、gid 或设置 unfollow=True"}
