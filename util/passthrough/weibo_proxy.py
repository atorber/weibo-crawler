#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Native Weibo API pass-through proxy.

Exposes 1:1 native request/response forwarding so local clients can replace
``https://weibo.com``, ``https://picupload.weibo.com``, or ``https://m.weibo.cn``
with this service's host and port (e.g. ``http://127.0.0.1:15001``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from urllib.parse import urlencode
import zlib

import requests
from requests.exceptions import RequestException

from util.browser_cookie import extract_and_save_cookie, get_cookie_auto_config
from util.publish.weibo_publisher import (
    DEFAULT_CLIENT_VERSION,
    DEFAULT_SERVER_VERSION,
    DEFAULT_USER_AGENT,
    PLACEHOLDER_COOKIES,
    _default_project_root,
    resolve_active_cookie,
)

logger = logging.getLogger("weibo.passthrough")

WEIBO_AUTH_COOKIE_KEYS = {"SUB", "SUBP", "XSRF-TOKEN", "SCF", "SSOLoginState"}

ALLOWED_MOBILE_EXACT_PATHS = {
    "api/container/getIndex",
    "api/config",
    "api/comments/show",
    "api/statuses/repostTimeline",
    "comments/hotflow",
    "comments/hotFlowChild",
    "statuses/show",
}
_MOBILE_DETAIL_RE = re.compile(r"^detail/[A-Za-z0-9_-]+$")
_SAFE_SUBPATH_RE = re.compile(r"^[A-Za-z0-9_.\-/]+$")

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
    "set-cookie",
}


def is_safe_subpath(subpath: str) -> bool:
    """Validate relative URL subpath to prevent SSRF, scheme injection, and traversal."""
    if not isinstance(subpath, str) or not subpath:
        return False
    if any(ord(ch) <= 32 or ord(ch) == 127 for ch in subpath):
        return False
    if subpath.startswith("/") or "//" in subpath or "\\" in subpath:
        return False
    if not _SAFE_SUBPATH_RE.fullmatch(subpath):
        return False
    segments = subpath.split("/")
    if len(segments) > 1 and any(seg == "" for seg in segments[:-1]):
        return False
    for seg in segments:
        if seg in (".", ".."):
            return False
    return True


def is_allowed_mobile_path(path: str) -> bool:
    """Validate that a mobile m.weibo.cn pass-through path is in the project allowlist."""
    raw = str(path or "")
    normalized = raw[1:] if raw.startswith("/") and not raw.startswith("//") else raw
    if not is_safe_subpath(normalized):
        return False
    normalized = normalized.rstrip("/")
    return normalized in ALLOWED_MOBILE_EXACT_PATHS or bool(
        _MOBILE_DETAIL_RE.fullmatch(normalized)
    )


def clean_weibo_params(data: dict) -> dict:
    """Drop empty strings / None / False while preserving integer 0 and JSON-encoding nested objects.

    Mirrors ``weibo-pro-next``'s ``cleanRequest`` helper.
    """
    if not isinstance(data, dict):
        return {}
    cleaned: dict = {}
    for k, v in data.items():
        if v is None or v == "" or v is False:
            continue
        if isinstance(v, (dict, list)):
            cleaned[k] = json.dumps(v, ensure_ascii=False)
        else:
            cleaned[k] = v
    return cleaned


def _parse_cookie_header(cookie_str: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in str(cookie_str or "").split(";"):
        if "=" not in part:
            continue
        k, v = part.strip().split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            parsed[k] = v
    return parsed


def _get_header_ci(headers: dict | None, target: str) -> str:
    if not headers:
        return ""
    target_l = target.lower()
    for k, v in headers.items():
        if str(k).lower() == target_l and v is not None:
            return str(v)
    return ""


def _extract_caller_cookie(headers: dict | None) -> str:
    explicit = _get_header_ci(headers, "X-Weibo-Cookie").strip()
    if explicit:
        return explicit
    raw_cookie = _get_header_ci(headers, "Cookie").strip()
    if not raw_cookie:
        return ""
    parsed = _parse_cookie_header(raw_cookie)
    if any(k in WEIBO_AUTH_COOKIE_KEYS for k in parsed):
        return raw_cookie
    return ""


def _normalize_query_params(query_params) -> list[tuple[str, str]]:
    if not query_params:
        return []
    if isinstance(query_params, list):
        return [(str(k), str(v)) for k, v in query_params if v is not None]
    if isinstance(query_params, dict):
        pairs: list[tuple[str, str]] = []
        for k, v in query_params.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple)):
                for item in v:
                    if item is not None:
                        pairs.append((str(k), str(item)))
            else:
                pairs.append((str(k), str(v)))
        return pairs
    return []


def _extract_xsrf_from_cookies(cookies_obj, parsed_cookies: dict[str, str]) -> str:
    token = parsed_cookies.get("XSRF-TOKEN", "")
    if isinstance(cookies_obj, dict):
        if cookies_obj.get("XSRF-TOKEN"):
            token = str(cookies_obj["XSRF-TOKEN"])
        return token
    weibo_com_token = ""
    fallback_token = ""
    try:
        for c in cookies_obj or []:
            if getattr(c, "name", None) == "XSRF-TOKEN" and getattr(c, "value", None):
                dom = str(getattr(c, "domain", "") or "").lower()
                if "weibo.com" in dom:
                    weibo_com_token = str(c.value)
                elif not dom:
                    fallback_token = str(c.value)
                elif not fallback_token:
                    fallback_token = str(c.value)
    except Exception:
        pass
    return weibo_com_token or fallback_token or token


def _response_json_safe(resp) -> dict | None:
    content_type = ""
    headers = getattr(resp, "headers", None) or {}
    content_type = _get_header_ci(headers, "Content-Type").lower()
    raw_bytes = getattr(resp, "content", None)
    if isinstance(raw_bytes, bytes):
        stripped = raw_bytes.lstrip()
        looks_json = ("json" in content_type) or stripped.startswith((b"{", b"["))
        if not looks_json:
            return None
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    if hasattr(resp, "json"):
        try:
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def _resp_bytes_and_headers(resp, upstream_url: str) -> tuple[int, dict[str, str], bytes]:
    status_code = int(getattr(resp, "status_code", 200))
    raw_content = getattr(resp, "content", None)
    if raw_content is None:
        text = getattr(resp, "text", None)
        if text is not None:
            raw_content = str(text).encode("utf-8")
        elif hasattr(resp, "json"):
            try:
                raw_content = json.dumps(resp.json(), ensure_ascii=False).encode("utf-8")
            except Exception:
                raw_content = b""
        else:
            raw_content = b""
    elif isinstance(raw_content, str):
        raw_content = raw_content.encode("utf-8")

    out_headers: dict[str, str] = {}
    upstream_headers = getattr(resp, "headers", None) or {}
    for k, v in upstream_headers.items():
        kl = str(k).lower()
        if kl in _HOP_BY_HOP_HEADERS:
            continue
        out_headers[str(k)] = str(v)

    if "content-type" not in {k.lower() for k in out_headers}:
        out_headers["Content-Type"] = "application/json; charset=utf-8"
    out_headers["X-Weibo-Passthrough-Upstream"] = upstream_url
    return status_code, out_headers, raw_content


def _json_error_response(
    status_code: int, message: str, upstream_url: str = ""
) -> tuple[int, dict[str, str], bytes]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if upstream_url:
        headers["X-Weibo-Passthrough-Upstream"] = upstream_url
    payload = json.dumps({"ok": 0, "msg": message}, ensure_ascii=False).encode("utf-8")
    return status_code, headers, payload


def _read_uploaded_file_bytes(file_obj) -> tuple[str, bytes, str]:
    filename = getattr(file_obj, "filename", None) or "upload.jpg"
    mime = getattr(file_obj, "mimetype", None) or "application/octet-stream"
    if isinstance(file_obj, (bytes, bytearray)):
        return filename, bytes(file_obj), mime
    if isinstance(file_obj, tuple):
        # Supports (filename, content_bytes[, mime]) or (filename, stream[, mime])
        fname = str(file_obj[0] or filename)
        content = file_obj[1]
        fmime = str(file_obj[2]) if len(file_obj) > 2 and file_obj[2] else mime
        if hasattr(content, "read"):
            raw = content.read()
            if hasattr(content, "seek"):
                try:
                    content.seek(0)
                except Exception:
                    pass
            return fname, bytes(raw), fmime
        return fname, bytes(content), fmime
    stream = getattr(file_obj, "stream", None) or file_obj
    if hasattr(stream, "seek"):
        try:
            stream.seek(0)
        except Exception:
            pass
    raw = stream.read()
    if hasattr(stream, "seek"):
        try:
            stream.seek(0)
        except Exception:
            pass
    return filename, bytes(raw), mime


class WeiboPassthroughProxy:
    """Thread-safe native Weibo HTTP pass-through client."""

    def __init__(
        self,
        project_root: str | None = None,
        session: requests.Session | None = None,
        auto_refresh: bool = True,
        timeout: int = 20,
    ):
        self.project_root = os.path.abspath(project_root or _default_project_root())
        self.timeout = timeout
        self.auto_refresh = auto_refresh
        self._injected_session = session is not None
        self.session = session or requests.Session()
        self._lock = threading.RLock()

        self._cookie_str: str = ""
        self.cookie_file_path: str | None = None
        self._parsed_cookies: dict[str, str] = {}
        self._uid: str = ""

        self._reload_project_cookie_if_needed(force=True)

    def _apply_cookie_string(self, cookie_str: str) -> None:
        self._parsed_cookies = _parse_cookie_header(cookie_str)
        cookies_obj = getattr(self.session, "cookies", None)
        if cookies_obj is None:
            return
        if hasattr(cookies_obj, "clear"):
            try:
                cookies_obj.clear()
            except Exception:
                pass
        if not hasattr(cookies_obj, "set"):
            return
        for k, v in self._parsed_cookies.items():
            try:
                cookies_obj.set(k, v, domain=".weibo.cn", path="/")
                cookies_obj.set(k, v, domain=".weibo.com", path="/")
            except TypeError:
                cookies_obj.set(k, v)

    def _reload_project_cookie_if_needed(self, force: bool = False) -> None:
        with self._lock:
            resolved_cookie, resolved_file = resolve_active_cookie(self.project_root)
            if resolved_file is not None:
                self.cookie_file_path = resolved_file
            if resolved_cookie and (force or resolved_cookie != self._cookie_str):
                self._cookie_str = resolved_cookie
                self._apply_cookie_string(resolved_cookie)
                self._uid = ""
            elif force and not self._cookie_str:
                self._cookie_str = ""
                self._parsed_cookies = {}

    def _latest_xsrf_token(self, caller_cookie: str = "") -> str:
        if caller_cookie:
            return _parse_cookie_header(caller_cookie).get("XSRF-TOKEN", "")
        return _extract_xsrf_from_cookies(
            getattr(self.session, "cookies", None), self._parsed_cookies
        )

    def _session_request(
        self,
        method: str,
        url: str,
        caller_cookie: str = "",
        **kwargs,
    ):
        if caller_cookie and not self._injected_session:
            req_headers = dict(kwargs.pop("headers", {}) or {})
            req_headers["Cookie"] = caller_cookie
            with requests.Session() as isolated:
                return isolated.request(method, url, headers=req_headers, **kwargs)

        if caller_cookie:
            req_headers = dict(kwargs.pop("headers", {}) or {})
            req_headers["Cookie"] = caller_cookie
            kwargs["headers"] = req_headers
        elif self._cookie_str and not hasattr(getattr(self.session, "cookies", None), "set"):
            req_headers = dict(kwargs.pop("headers", {}) or {})
            req_headers.setdefault("Cookie", self._cookie_str)
            kwargs["headers"] = req_headers

        if hasattr(self.session, "request"):
            return self.session.request(method, url, **kwargs)
        method_u = method.upper()
        if method_u == "GET":
            return self.session.get(url, **kwargs)
        if method_u == "POST":
            return self.session.post(url, **kwargs)
        raise RequestException(f"测试会话不支持 HTTP 方法: {method_u}")

    def _try_browser_refresh(self, prefer_domain: str = "weibo.com") -> bool:
        if not self.auto_refresh:
            return False
        try:
            auto_cfg = get_cookie_auto_config()
        except Exception:
            auto_cfg = {}
        if not (auto_cfg.get("enabled") and auto_cfg.get("refresh_on_expire")):
            return False

        browser = auto_cfg.get("browser", "auto")
        logger.warning(
            "透传接口检测到登录态失效，尝试定向提取 %s 的 %s Cookie...",
            browser,
            prefer_domain,
        )
        try:
            res = extract_and_save_cookie(
                browser_name=browser,
                cookie_file_path=self.cookie_file_path,
                prefer_domain=prefer_domain,
            )
        except Exception as exc:
            logger.warning("透传接口刷新 Cookie 失败: %s", exc)
            return False

        new_cookie = (res or {}).get("cookie")
        if not (res and res.get("success") and res.get("valid") and new_cookie):
            return False

        with self._lock:
            self._cookie_str = new_cookie
            self._apply_cookie_string(new_cookie)
            self._uid = ""
        return True

    def _handshake_xsrf(self, caller_cookie: str = "") -> str:
        try:
            self._session_request(
                "GET",
                "https://weibo.com/ajax/statuses/config",
                caller_cookie=caller_cookie,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://weibo.com/",
                    "Origin": "https://weibo.com",
                    "X-Requested-With": "XMLHttpRequest",
                    "client-version": DEFAULT_CLIENT_VERSION,
                    "server-version": DEFAULT_SERVER_VERSION,
                },
                timeout=self.timeout,
                allow_redirects=False,
            )
        except RequestException as exc:
            logger.debug("statuses/config 握手异常: %s", exc)
        return self._latest_xsrf_token(caller_cookie=caller_cookie)

    def _ensure_uid(self, caller_cookie: str = "") -> str:
        if self._uid and not caller_cookie:
            return self._uid
        xsrf = self._latest_xsrf_token(caller_cookie=caller_cookie) or self._handshake_xsrf(
            caller_cookie=caller_cookie
        )
        req_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://weibo.com/",
            "Origin": "https://weibo.com",
            "X-Requested-With": "XMLHttpRequest",
            "client-version": DEFAULT_CLIENT_VERSION,
            "server-version": DEFAULT_SERVER_VERSION,
        }
        if xsrf:
            req_headers["X-XSRF-TOKEN"] = xsrf
        try:
            resp = self._session_request(
                "GET",
                "https://weibo.com/ajax/profile/detail",
                caller_cookie=caller_cookie,
                headers=req_headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
            js = _response_json_safe(resp) or {}
            if js.get("ok") == 1:
                data = js.get("data") if isinstance(js.get("data"), dict) else {}
                uid = ""
                m = re.search(r"uid=(\d+)", str(data.get("verified_url") or ""))
                if m:
                    uid = m.group(1)
                elif data.get("uid"):
                    uid = str(data.get("uid"))
                if uid and not caller_cookie:
                    self._uid = uid
                return uid
        except RequestException as exc:
            logger.debug("获取登录 UID 失败: %s", exc)
        return ""

    @staticmethod
    def _needs_ajax_retry(resp) -> tuple[bool, bool]:
        """Return (should_retry, is_auth_expired)."""
        status = int(getattr(resp, "status_code", 200))
        js = _response_json_safe(resp) or {}
        ok_val = js.get("ok")
        msg = str(js.get("msg") or "").lower()
        is_auth_expired = ok_val == -100 or status in (401, 403, 432)
        is_xsrf_issue = status in (400, 403, 419) or "xsrf" in msg
        return (is_auth_expired or is_xsrf_issue), is_auth_expired

    def proxy_weibo_ajax(
        self,
        subpath: str,
        method: str = "GET",
        query_params=None,
        headers: dict | None = None,
        body: bytes | str | None = None,
        json_body=None,
        form_data: dict | None = None,
        files=None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Forward native requests under ``https://weibo.com/ajax/<subpath>``."""
        raw_subpath = str(subpath or "")
        if not is_safe_subpath(raw_subpath):
            return _json_error_response(400, f"非法微博 AJAX 路径: {subpath!r}")

        clean_subpath = raw_subpath
        target_url = f"https://weibo.com/ajax/{clean_subpath}"
        method_u = str(method or "GET").upper()
        caller_cookie = _extract_caller_cookie(headers)
        if not caller_cookie:
            self._reload_project_cookie_if_needed()

        caller_xsrf = _get_header_ci(headers, "X-XSRF-TOKEN").strip()
        xsrf = caller_xsrf or self._latest_xsrf_token(caller_cookie=caller_cookie)
        if (
            method_u in ("POST", "PUT", "PATCH", "DELETE")
            and not xsrf
            and not caller_xsrf
        ):
            xsrf = self._handshake_xsrf(caller_cookie=caller_cookie)

        params_list = _normalize_query_params(query_params)

        def _build_req_kwargs(current_xsrf: str) -> dict:
            req_headers = {
                "User-Agent": _get_header_ci(headers, "User-Agent") or DEFAULT_USER_AGENT,
                "Accept": _get_header_ci(headers, "Accept")
                or "application/json, text/plain, */*",
                "Referer": "https://weibo.com/",
                "Origin": "https://weibo.com",
                "X-Requested-With": "XMLHttpRequest",
                "client-version": _get_header_ci(headers, "client-version")
                or DEFAULT_CLIENT_VERSION,
                "server-version": _get_header_ci(headers, "server-version")
                or DEFAULT_SERVER_VERSION,
            }
            if current_xsrf:
                req_headers["X-XSRF-TOKEN"] = current_xsrf

            req_kw: dict = {
                "params": params_list or None,
                "headers": req_headers,
                "timeout": self.timeout,
                "allow_redirects": False,
            }

            if method_u in ("POST", "PUT", "PATCH", "DELETE"):
                raw_mode = _get_header_ci(headers, "X-Weibo-Raw-Body").strip().lower() in (
                    "1",
                    "true",
                )
                if files:
                    multipart_files = {}
                    for field_key, f_val in files.items():
                        fname, fbytes, fmime = _read_uploaded_file_bytes(f_val)
                        multipart_files[field_key] = (fname, fbytes, fmime)
                    req_kw["files"] = multipart_files
                    if form_data:
                        req_kw["data"] = form_data
                elif isinstance(json_body, dict) and not raw_mode:
                    cleaned = clean_weibo_params(json_body)
                    req_headers["Content-Type"] = (
                        "application/x-www-form-urlencoded; charset=UTF-8"
                    )
                    req_kw["data"] = urlencode(cleaned, doseq=True)
                elif body not in (None, b"", ""):
                    req_headers["Content-Type"] = (
                        _get_header_ci(headers, "Content-Type")
                        or "application/x-www-form-urlencoded; charset=UTF-8"
                    )
                    req_kw["data"] = body
                elif form_data:
                    req_headers["Content-Type"] = (
                        "application/x-www-form-urlencoded; charset=UTF-8"
                    )
                    req_kw["data"] = urlencode(form_data, doseq=True)

            return req_kw

        try:
            resp = self._session_request(
                method_u,
                target_url,
                caller_cookie=caller_cookie,
                **_build_req_kwargs(xsrf),
            )
        except RequestException as exc:
            return _json_error_response(502, f"请求上游失败: {exc}", upstream_url=target_url)

        should_retry, is_auth_expired = self._needs_ajax_retry(resp)
        if (
            should_retry
            and not caller_cookie
            and not caller_xsrf
            and self.auto_refresh
        ):
            old_xsrf = xsrf
            old_cookie = self._cookie_str
            new_xsrf = self._handshake_xsrf()
            if (is_auth_expired and new_xsrf == old_xsrf) or (
                (_response_json_safe(resp) or {}).get("ok") == -100
            ):
                if self._try_browser_refresh(prefer_domain="weibo.com"):
                    new_xsrf = self._handshake_xsrf()
            if (new_xsrf and new_xsrf != old_xsrf) or self._cookie_str != old_cookie:
                try:
                    resp = self._session_request(
                        method_u,
                        target_url,
                        caller_cookie=caller_cookie,
                        **_build_req_kwargs(new_xsrf),
                    )
                except RequestException as exc:
                    return _json_error_response(
                        502, f"重试上游失败: {exc}", upstream_url=target_url
                    )

        return _resp_bytes_and_headers(resp, target_url)

    def proxy_picupload(
        self,
        endpoint: str = "upload.php",
        query_params=None,
        headers: dict | None = None,
        body: bytes | None = None,
        files=None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Forward native requests to ``https://picupload.weibo.com/interface/<endpoint>``."""
        ep = str(endpoint or "").strip().lstrip("/")
        if ep not in ("upload.php", "pic_upload.php"):
            return _json_error_response(400, f"不支持的图床透传端点: {endpoint!r}")

        caller_cookie = _extract_caller_cookie(headers)
        if not caller_cookie:
            self._reload_project_cookie_if_needed()

        caller_pairs = _normalize_query_params(query_params)
        caller_param_map = {k: v for k, v in caller_pairs}

        def _base_headers() -> dict[str, str]:
            return {
                "User-Agent": _get_header_ci(headers, "User-Agent") or DEFAULT_USER_AGENT,
                "Referer": "https://weibo.com/",
                "Origin": "https://weibo.com",
            }

        if ep == "upload.php":
            raw = bytes(body or b"")
            if not raw and files:
                first_file = files.get("file") or files.get("pic1") or next(iter(files.values()))
                _, raw, _ = _read_uploaded_file_bytes(first_file)
            if not raw:
                return _json_error_response(
                    400,
                    "请通过原始二进制请求体或 multipart (file/pic1) 上传图片内容",
                )

            uid_val = caller_param_map.get("uid") or self._ensure_uid(caller_cookie=caller_cookie)
            defaults = {
                "file_source": "1",
                "cs": str(zlib.crc32(raw) & 0xFFFFFFFF),
                "ent": "miniblog",
                "appid": "339644097",
                "uid": str(uid_val or ""),
                "raw_md5": hashlib.md5(raw).hexdigest(),
                "ori": "1",
                "pri": "0",
                "request_id": str(int(time.time() * 1000)),
                "file_size": str(len(raw)),
            }
            merged = dict(defaults)
            merged.update(caller_param_map)

            hosts = ("picupload.weibo.com", "i.api.weibo.com")
            last_resp = None
            last_url = f"https://{hosts[0]}/interface/upload.php"
            last_exc: Exception | None = None

            for idx, host in enumerate(hosts):
                target_url = f"https://{host}/interface/upload.php"
                last_url = target_url
                req_headers = _base_headers()
                req_headers["Content-Type"] = "application/octet-stream"
                try:
                    resp = self._session_request(
                        "POST",
                        target_url,
                        caller_cookie=caller_cookie,
                        params=merged,
                        data=raw,
                        headers=req_headers,
                        timeout=max(self.timeout, 60),
                        allow_redirects=False,
                    )
                    last_resp = resp
                    if resp.status_code >= 500 and idx == 0:
                        continue
                    js = _response_json_safe(resp) or {}
                    if (
                        js.get("ret") is False
                        and js.get("errno") in (1, -1)
                        and not caller_cookie
                        and self.auto_refresh
                        and self._try_browser_refresh(prefer_domain="weibo.com")
                    ):
                        refreshed_uid = self._ensure_uid()
                        if refreshed_uid:
                            merged["uid"] = refreshed_uid
                        resp = self._session_request(
                            "POST",
                            target_url,
                            caller_cookie=caller_cookie,
                            params=merged,
                            data=raw,
                            headers=req_headers,
                            timeout=max(self.timeout, 60),
                            allow_redirects=False,
                        )
                    return _resp_bytes_and_headers(resp, target_url)
                except RequestException as exc:
                    last_exc = exc
                    continue

            if last_resp is not None:
                return _resp_bytes_and_headers(last_resp, last_url)
            return _json_error_response(
                502, f"图床透传请求失败: {last_exc}", upstream_url=last_url
            )

        # pic_upload.php
        target_url = "https://picupload.weibo.com/interface/pic_upload.php"
        merged = {"app": "miniblog", "s": "json", "p": "1", "data": "1"}
        merged.update(caller_param_map)
        req_headers = _base_headers()

        def _send_pic_upload():
            if files:
                multipart_files = {}
                for field_key, f_val in files.items():
                    fname, fbytes, fmime = _read_uploaded_file_bytes(f_val)
                    mapped_key = "pic1" if (field_key == "file" and "pic1" not in files) else field_key
                    multipart_files[mapped_key] = (fname, fbytes, fmime)
                return self._session_request(
                    "POST",
                    target_url,
                    caller_cookie=caller_cookie,
                    params=merged,
                    files=multipart_files,
                    headers=req_headers,
                    timeout=max(self.timeout, 60),
                    allow_redirects=False,
                )
            ct = _get_header_ci(headers, "Content-Type")
            if ct:
                req_headers["Content-Type"] = ct
            return self._session_request(
                "POST",
                target_url,
                caller_cookie=caller_cookie,
                params=merged,
                data=bytes(body or b""),
                headers=req_headers,
                timeout=max(self.timeout, 60),
                allow_redirects=False,
            )

        try:
            resp = _send_pic_upload()
        except RequestException as exc:
            return _json_error_response(502, f"备用图床透传失败: {exc}", upstream_url=target_url)

        return _resp_bytes_and_headers(resp, target_url)

    def proxy_mobile_weibo(
        self,
        path: str,
        method: str = "GET",
        query_params=None,
        headers: dict | None = None,
        body: bytes | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Forward native requests to allowlisted ``https://m.weibo.cn/*`` endpoints."""
        raw_path = str(path or "")
        normalized = (
            raw_path[1:]
            if raw_path.startswith("/") and not raw_path.startswith("//")
            else raw_path
        )
        if not is_safe_subpath(normalized):
            return _json_error_response(400, f"非法 m.weibo.cn 路径: {path!r}")
        if not is_allowed_mobile_path(normalized):
            return _json_error_response(403, f"路径不在 m.weibo.cn 透传白名单中: /{normalized}")

        target_url = f"https://m.weibo.cn/{normalized}"
        method_u = str(method or "GET").upper()
        caller_cookie = _extract_caller_cookie(headers)
        if not caller_cookie:
            self._reload_project_cookie_if_needed()

        is_detail_page = normalized.startswith("detail/")
        params_list = _normalize_query_params(query_params)

        def _build_mobile_headers() -> dict[str, str]:
            h = {
                "User-Agent": _get_header_ci(headers, "User-Agent") or DEFAULT_USER_AGENT,
                "Referer": "https://m.weibo.cn/",
            }
            if is_detail_page:
                h["Accept"] = (
                    _get_header_ci(headers, "Accept")
                    or "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                )
            else:
                h["Accept"] = _get_header_ci(headers, "Accept") or "application/json, text/plain, */*"
                h["X-Requested-With"] = "XMLHttpRequest"
            return h

        req_kwargs: dict = {
            "params": params_list or None,
            "headers": _build_mobile_headers(),
            "timeout": self.timeout,
            "allow_redirects": False,
        }
        if method_u in ("POST", "PUT", "PATCH", "DELETE") and body:
            req_kwargs["data"] = body

        try:
            resp = self._session_request(
                method_u, target_url, caller_cookie=caller_cookie, **req_kwargs
            )
        except RequestException as exc:
            return _json_error_response(
                502, f"请求 m.weibo.cn 上游失败: {exc}", upstream_url=target_url
            )

        js = _response_json_safe(resp) or {}
        if (
            (resp.status_code in (401, 403, 432) or js.get("ok") == -100)
            and not caller_cookie
            and self.auto_refresh
            and self._try_browser_refresh(prefer_domain="weibo.cn")
        ):
            try:
                resp = self._session_request(
                    method_u, target_url, caller_cookie=caller_cookie, **req_kwargs
                )
            except RequestException as exc:
                return _json_error_response(
                    502, f"重试 m.weibo.cn 上游失败: {exc}", upstream_url=target_url
                )

        return _resp_bytes_and_headers(resp, target_url)
