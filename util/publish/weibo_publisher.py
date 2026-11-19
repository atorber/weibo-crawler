#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Weibo PC web publishing & post management client.

Protocol derived from REA analysis of https://weibo.com/ (weibo-pro-next v1.1.260):
- Auth & XSRF handshake: GET /ajax/statuses/config, GET /ajax/profile/detail
- Publish immediately:     POST /ajax/statuses/update
- Publish scheduled:       POST /ajax/statuses/schedule/upload
- Edit post:               GET /ajax/statuses/checkCanEdit, POST /ajax/statuses/modify
- Modify visibility:       POST /ajax/statuses/modifyVisible (ids, visible)
- Delete post:             POST /ajax/statuses/destroy (id)
- List own posts:          GET /ajax/statuses/mymblog (uid, page, feature)
- Upload image:            POST //picupload.weibo.com/interface/upload.php (octet-stream)
                           fallback: //picupload.weibo.com/interface/pic_upload.php (multipart)
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import logging
import mimetypes
import os
import re
import time
from urllib.parse import urlparse
import zlib

try:
    import json5
except ImportError:
    json5 = None

import requests
from requests.exceptions import RequestException

from util.browser_cookie import extract_and_save_cookie, get_cookie_auto_config
from util.config import config_paths

logger = logging.getLogger("weibo.publish")

DEFAULT_CLIENT_VERSION = "v1.1.260"
DEFAULT_SERVER_VERSION = "v2026.11.18.1"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

VISIBLE_OPTIONS: dict[int, str] = {
    0: "公开",
    1: "仅自己可见",
    6: "好友圈",
    10: "粉丝可见",
    5: "群可见",
}

MAX_IMAGES = 18
MAX_IMAGE_BYTES = 20 * 1024 * 1024
PLACEHOLDER_COOKIES = {"", "your cookie", "YOUR_WEIBO_COOKIE_HERE"}
ALLOWED_IMAGE_DOMAIN_SUFFIXES = (".sinaimg.cn", ".weibocdn.com")

MIME_BY_EXT: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

UPLOAD_ERROR_MESSAGES: dict[int, str] = {
    1: "用户未登录",
    2: "上传数据无效",
    3: "回调地址无效",
    4: "未找到上传文件",
    5: "无权上传",
    6: "上传 uid 无效",
    7: "未指定返回信息类型",
    8: "上传数据出错",
    9: "上传 MIME 类型不支持",
    10: "上传文件大小无效",
    11: "存储出错",
    12: "上传 EXIF 信息过长",
    13: "上传回调出错",
    14: "回调返回出错",
    15: "错误的请求",
    -1: "没有登录",
    -2: "没有收到 POST 数据",
    -3: "没有指定 cb 参数",
    -4: "没有发现提交上传文件",
    -5: "该 app 没有开放图片上传服务",
    -6: "uid 非法",
    -7: "参数 s 值不支持",
    -8: "数据上传失败",
    -9: "文件 MIME 类型不支持",
    -10: "文件字节数超过限制",
    -11: "存储错误",
    -12: "图片 EXIF 信息超长(2k)",
}


def _default_project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def _parse_config_text(raw: str) -> dict:
    if not raw.strip():
        return {}
    if json5 is not None:
        try:
            data = json5.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    m = re.search(r'"cookie"\s*:\s*"([^"]*)"', raw)
    return {"cookie": m.group(1)} if m else {}


def resolve_active_cookie(project_root: str | None = None) -> tuple[str, str | None]:
    """Resolve current Weibo Cookie string and optional backing .txt file path.

    Priority:
        1. ``WEIBO_COOKIE`` environment variable
        2. ``cookie`` field in ``config/config.json`` (or root ``config.json`` fallback)
    """
    env_cookie = (os.environ.get("WEIBO_COOKIE") or "").strip()
    if env_cookie and env_cookie not in PLACEHOLDER_COOKIES:
        return env_cookie, None

    root = os.path.abspath(project_root or _default_project_root())
    config_path, example_path = config_paths.config_files(root)
    target_path = config_path if os.path.isfile(config_path) else example_path
    if not os.path.isfile(target_path):
        return "", None

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return "", None

    parsed = _parse_config_text(raw)
    cookie_val = parsed.get("cookie", "")
    if not isinstance(cookie_val, str):
        return "", None

    cookie_val = cookie_val.strip()
    if cookie_val.endswith(".txt"):
        resolved_txt = config_paths.resolve_config_file(root, cookie_val)
        if os.path.isfile(resolved_txt):
            try:
                with open(resolved_txt, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text in PLACEHOLDER_COOKIES:
                    text = ""
                return text, resolved_txt
            except OSError:
                return "", resolved_txt
        return "", resolved_txt

    if cookie_val in PLACEHOLDER_COOKIES:
        return "", None
    return cookie_val, None


def parse_schedule_timestamp(schedule_time, now_ms: int | None = None) -> int:
    """Parse schedule time input into epoch milliseconds and validate >= 10 min lead time."""
    if schedule_time is None or schedule_time == "":
        raise ValueError("定时发布时间不能为空")

    if isinstance(schedule_time, bool):
        raise ValueError("定时发布时间格式无效")

    ts_ms: int
    if isinstance(schedule_time, (int, float)):
        val = float(schedule_time)
        ts_ms = int(val * 1000) if val < 1e12 else int(val)
    elif isinstance(schedule_time, str):
        text = schedule_time.strip()
        if text.isdigit():
            num = int(text)
            ts_ms = num * 1000 if num < 10**12 else num
        else:
            normalized = text.replace("T", " ").replace("/", "-")
            dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(normalized, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                try:
                    dt = datetime.fromisoformat(text)
                except ValueError as exc:
                    raise ValueError(
                        f"定时发布时间格式无效: {schedule_time!r}（支持 YYYY-MM-DD HH:MM 或毫秒时间戳）"
                    ) from exc
            ts_ms = int(dt.timestamp() * 1000)
    else:
        raise ValueError(f"定时发布时间类型不支持: {type(schedule_time).__name__}")

    current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if ts_ms - current_ms < 540_000:
        raise ValueError("只能发送至少 10 分钟后的定时微博")
    return ts_ms


def _clean_form(data: dict) -> dict:
    """Drop empty strings / None while preserving integer 0 (matches weibo-pro-next cleanRequest)."""
    return {k: v for k, v in data.items() if v is not None and v != ""}


def normalize_weibo_image_url(url: str) -> str:
    """Normalize protocol-relative or whitespace-padded Weibo image URLs."""
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        return "https:" + text
    return text


def is_allowed_weibo_image_url(url: str) -> bool:
    """Allow only official Weibo image/media CDN hosts to prevent SSRF."""
    normalized = normalize_weibo_image_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        return False
    return any(host.endswith(suffix) for suffix in ALLOWED_IMAGE_DOMAIN_SUFFIXES)


def _guess_mime(filename: str | None) -> str:
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in MIME_BY_EXT:
            return MIME_BY_EXT[ext]
        guessed, _ = mimetypes.guess_type(filename)
        if guessed and guessed.startswith("image/"):
            return guessed
    return "image/jpeg"


class WeiboPublisher:
    """Client for Weibo PC web post creation, image upload, edit, visibility and deletion."""

    def __init__(
        self,
        cookie: str | None = None,
        project_root: str | None = None,
        session: requests.Session | None = None,
        auto_refresh: bool = True,
        timeout: int = 15,
    ):
        self.project_root = os.path.abspath(project_root or _default_project_root())
        self.timeout = timeout
        self.auto_refresh = auto_refresh
        self.cookie_file_path: str | None = None

        if cookie is None:
            resolved_cookie, resolved_file = resolve_active_cookie(self.project_root)
            self.cookie_str = resolved_cookie
            self.cookie_file_path = resolved_file
        else:
            self.cookie_str = str(cookie).strip()

        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://weibo.com/",
                "Origin": "https://weibo.com",
                "X-Requested-With": "XMLHttpRequest",
                "client-version": DEFAULT_CLIENT_VERSION,
                "server-version": DEFAULT_SERVER_VERSION,
            }
        )

        self._parsed_cookies: dict[str, str] = {}
        if self.cookie_str:
            self._apply_cookie_string(self.cookie_str)

        self._uid: str = ""
        self._screen_name: str = ""
        self._session_ready: bool = False

    def _apply_cookie_string(self, cookie_str: str) -> None:
        self._parsed_cookies = {}
        try:
            self.session.cookies.clear()
        except Exception:
            pass
        for part in str(cookie_str or "").split(";"):
            if "=" not in part:
                continue
            k, v = part.strip().split("=", 1)
            k = k.strip()
            v = v.strip()
            if not k:
                continue
            self._parsed_cookies[k] = v
            try:
                self.session.cookies.set(k, v, domain=".weibo.com", path="/")
            except TypeError:
                self.session.cookies.set(k, v)

    def _latest_xsrf_token(self) -> str:
        token = self._parsed_cookies.get("XSRF-TOKEN", "")
        for c in getattr(self.session, "cookies", []):
            if getattr(c, "name", None) == "XSRF-TOKEN" and getattr(c, "value", None):
                token = c.value
        return token

    def _sync_xsrf_header(self) -> str:
        token = self._latest_xsrf_token()
        if token:
            self.session.headers["X-XSRF-TOKEN"] = token
        return token

    def _try_browser_refresh(self) -> bool:
        if not self.auto_refresh:
            return False
        try:
            auto_cfg = get_cookie_auto_config()
        except Exception:
            auto_cfg = {}
        if not (auto_cfg.get("enabled") and auto_cfg.get("refresh_on_expire")):
            return False

        browser = auto_cfg.get("browser", "auto")
        logger.warning("weibo.com 登录态失效，尝试定向提取 %s 的 weibo.com Cookie...", browser)
        try:
            res = extract_and_save_cookie(
                browser_name=browser,
                cookie_file_path=self.cookie_file_path,
                prefer_domain="weibo.com",
            )
        except Exception as exc:
            logger.warning("定向刷新 weibo.com Cookie 失败: %s", exc)
            return False

        new_cookie = (res or {}).get("cookie")
        if not (res and res.get("success") and res.get("valid") and new_cookie):
            return False

        self.cookie_str = new_cookie
        self._apply_cookie_string(new_cookie)
        self._sync_xsrf_header()
        return True

    def ensure_session(self, force: bool = False) -> dict:
        """Verify weibo.com personal login state and refresh XSRF-TOKEN."""
        if self._session_ready and self._uid and not force:
            xsrf = self._sync_xsrf_header()
            return {
                "ok": True,
                "logged_in": True,
                "uid": self._uid,
                "screen_name": self._screen_name,
                "has_xsrf": bool(xsrf),
                "message": (
                    f"已登录：{self._screen_name or self._uid}"
                    if (self._screen_name or self._uid)
                    else "已登录"
                ),
            }

        if not self.cookie_str or self.cookie_str in PLACEHOLDER_COOKIES:
            if not self._try_browser_refresh():
                return {
                    "ok": False,
                    "logged_in": False,
                    "uid": "",
                    "screen_name": "",
                    "has_xsrf": False,
                    "message": "未配置有效微博 Cookie，请在设置页填入或一键从浏览器提取",
                }

        def _handshake() -> tuple[dict, int]:
            try:
                self.session.get(
                    "https://weibo.com/ajax/statuses/config",
                    timeout=self.timeout,
                )
            except RequestException as exc:
                logger.debug("statuses/config 握手异常: %s", exc)

            self._sync_xsrf_header()
            try:
                r_prof = self.session.get(
                    "https://weibo.com/ajax/profile/detail",
                    timeout=self.timeout,
                )
            except RequestException as exc:
                return {"_network_error": str(exc)}, 0

            self._sync_xsrf_header()
            try:
                js = r_prof.json()
            except ValueError:
                return {"_raw_text": getattr(r_prof, "text", "")[:200]}, r_prof.status_code
            return js, r_prof.status_code

        prof_json, status_code = _handshake()
        if prof_json.get("ok") != 1 and self._try_browser_refresh():
            prof_json, status_code = _handshake()

        if prof_json.get("_network_error"):
            return {
                "ok": False,
                "logged_in": False,
                "uid": "",
                "screen_name": "",
                "has_xsrf": bool(self._latest_xsrf_token()),
                "message": f"校验 weibo.com 登录态网络异常: {prof_json['_network_error']}",
            }

        if prof_json.get("ok") != 1:
            msg = prof_json.get("msg") or f"weibo.com 个人登录校验失败 (HTTP {status_code or '?'})"
            if not prof_json.get("_raw_text"):
                msg = f"weibo.com 个人登录未通过（请确认已登录 weibo.com 而非仅访客 Cookie）: {msg}"
            self._session_ready = False
            return {
                "ok": False,
                "logged_in": False,
                "uid": "",
                "screen_name": "",
                "has_xsrf": bool(self._latest_xsrf_token()),
                "message": msg,
            }

        prof_data = prof_json.get("data") if isinstance(prof_json.get("data"), dict) else {}
        uid = ""
        m_uid = re.search(r"uid=(\d+)", str(prof_data.get("verified_url") or ""))
        if m_uid:
            uid = m_uid.group(1)
        if not uid and prof_data.get("uid"):
            uid = str(prof_data.get("uid"))

        screen_name = ""
        if uid:
            try:
                r_info = self.session.get(
                    f"https://weibo.com/ajax/profile/info?uid={uid}",
                    timeout=self.timeout,
                )
                if r_info.status_code == 200:
                    info_js = r_info.json()
                    user_obj = (info_js.get("data") or {}).get("user") or {}
                    screen_name = str(user_obj.get("screen_name") or "")
            except Exception:
                pass

        xsrf = self._sync_xsrf_header()
        self._uid = uid
        self._screen_name = screen_name
        self._session_ready = True
        display = screen_name or (f"UID:{uid}" if uid else "已登录用户")
        return {
            "ok": True,
            "logged_in": True,
            "uid": uid,
            "screen_name": screen_name,
            "has_xsrf": bool(xsrf),
            "message": f"Cookie 具备 weibo.com 发布权限（账号：{display}）",
        }

    def _post_ajax(self, path: str, form_data: dict, retry_auth: bool = True) -> dict:
        url = f"https://weibo.com{path}"
        cleaned = _clean_form(form_data)
        self._sync_xsrf_header()

        try:
            resp = self.session.post(
                url,
                data=cleaned,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )
        except RequestException as exc:
            return {"ok": False, "msg": f"请求 {path} 失败: {exc}"}

        try:
            js = resp.json()
        except ValueError:
            return {
                "ok": False,
                "status_code": resp.status_code,
                "msg": f"接口 {path} 返回非 JSON 响应 (HTTP {resp.status_code})",
                "raw_text": getattr(resp, "text", "")[:300],
            }

        ok_val = js.get("ok")
        if ok_val == -100:
            if retry_auth and self._try_browser_refresh():
                self.ensure_session(force=True)
                return self._post_ajax(path, form_data, retry_auth=False)
            return {
                "ok": False,
                "logged_in": False,
                "msg": js.get("msg") or "weibo.com 登录已失效，请重新提取 Cookie",
                "raw": js,
            }

        data_obj = js.get("data") if isinstance(js.get("data"), dict) else {}
        if data_obj.get("verify"):
            return {
                "ok": False,
                "need_verify": True,
                "msg": "触发微博安全风控人机验证，请稍后在浏览器端完成验证或降低操作频率",
                "raw": js,
            }

        if js.get("error"):
            return {
                "ok": False,
                "msg": js.get("msg") or str(js.get("error")),
                "raw": js,
            }

        if not (isinstance(ok_val, (int, float)) and ok_val > 0):
            return {
                "ok": False,
                "msg": js.get("msg") or f"操作未成功 (ok={ok_val})",
                "raw": js,
            }

        return {"ok": True, "raw": js}

    @staticmethod
    def _validate_visible(visible) -> int:
        try:
            vis = int(visible)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"可见性参数必须是整数: {visible!r}") from exc
        if vis not in VISIBLE_OPTIONS:
            allowed = ", ".join(f"{k}={v}" for k, v in VISIBLE_OPTIONS.items())
            raise ValueError(f"不支持的可见性取值 {vis}，可选值：{allowed}")
        return vis

    def _upload_via_binary(
        self, host: str, raw: bytes, pri: int = 0
    ) -> tuple[str | None, str | None, bool]:
        """Upload raw image bytes to //<host>/interface/upload.php.

        Returns:
            (pid, error_message, should_retry_alternate_host)
        """
        cs = zlib.crc32(raw) & 0xFFFFFFFF
        raw_md5 = hashlib.md5(raw).hexdigest()
        req_id = int(time.time() * 1000)
        params = {
            "file_source": 1,
            "cs": cs,
            "ent": "miniblog",
            "appid": 339644097,
            "uid": self._uid,
            "raw_md5": raw_md5,
            "ori": 1,
            "pri": pri,
            "request_id": req_id,
            "file_size": len(raw),
        }
        url = f"https://{host}/interface/upload.php"
        # weibo-pro-next deletes X-Requested-With & skips X-XSRF-TOKEN on upload hosts
        headers = {
            "Content-Type": "application/octet-stream",
            "Referer": "https://weibo.com/",
            "Origin": "https://weibo.com",
            "X-Requested-With": None,
            "X-XSRF-TOKEN": None,
        }
        try:
            resp = self.session.post(
                url,
                params=params,
                data=raw,
                headers=headers,
                timeout=max(self.timeout, 60),
            )
            js = resp.json()
        except RequestException as exc:
            return None, f"图床请求异常 ({host}): {exc}", True
        except ValueError:
            return None, f"图床返回非 JSON 响应 ({host}, HTTP {resp.status_code})", False

        if js.get("ret") is True and isinstance(js.get("pic"), dict) and js["pic"].get("pid"):
            return str(js["pic"]["pid"]), None, False

        if js.get("ret") is False:
            errno = js.get("errno")
            reason = UPLOAD_ERROR_MESSAGES.get(errno) or UPLOAD_ERROR_MESSAGES.get(
                abs(errno) if isinstance(errno, int) else errno
            )
            return None, f"上传图片失败: {reason or '未知错误'} (errno={errno})", False

        return None, f"图床返回异常响应 ({host}): {js}", False

    def _upload_via_multipart(
        self, raw: bytes, filename: str, mime_type: str
    ) -> tuple[str | None, str | None]:
        url = "https://picupload.weibo.com/interface/pic_upload.php"
        params = {"app": "miniblog", "s": "json", "p": 1, "data": 1}
        headers = {
            "Referer": "https://weibo.com/",
            "Origin": "https://weibo.com",
            "X-Requested-With": None,
            "X-XSRF-TOKEN": None,
        }
        try:
            resp = self.session.post(
                url,
                params=params,
                files={"pic1": (filename, raw, mime_type)},
                headers=headers,
                timeout=max(self.timeout, 60),
            )
            js = resp.json()
        except (RequestException, ValueError) as exc:
            return None, f"备用图床上传失败: {exc}"

        if js.get("code") == "A00006":
            pid = (
                ((js.get("data") or {}).get("pics") or {}).get("pic_1") or {}
            ).get("pid")
            if pid:
                return str(pid), None

        if js.get("ret") is True and isinstance(js.get("pic"), dict) and js["pic"].get("pid"):
            return str(js["pic"]["pid"]), None

        return None, f"备用图床上传拒绝: {js}"

    def upload_image(
        self,
        file_path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        pri: int = 0,
    ) -> dict:
        """Upload one image to Weibo picture CDN and return pid & preview URL."""
        sess = self.ensure_session()
        if not sess.get("ok"):
            return {"ok": False, "msg": sess.get("message") or "未登录"}

        if data is None:
            if not file_path or not os.path.isfile(file_path):
                return {"ok": False, "msg": f"图片文件不存在: {file_path}"}
            with open(file_path, "rb") as f:
                raw = f.read()
            resolved_name = filename or os.path.basename(file_path)
        else:
            raw = bytes(data)
            resolved_name = filename or "image.jpg"

        if not raw:
            return {"ok": False, "msg": f"图片内容为空: {resolved_name}"}
        if len(raw) > MAX_IMAGE_BYTES:
            return {"ok": False, "msg": f"图片超过 20MB 限制: {resolved_name}"}

        resolved_mime = mime_type or _guess_mime(resolved_name)

        pid, err, retry_alt = self._upload_via_binary(
            "picupload.weibo.com", raw, pri=pri
        )
        if not pid and retry_alt:
            pid, err, _ = self._upload_via_binary(
                "image.api.weibo.com", raw, pri=pri
            )
        if not pid:
            fb_pid, fb_err = self._upload_via_multipart(
                raw, resolved_name, resolved_mime
            )
            if fb_pid:
                pid = fb_pid
            else:
                return {"ok": False, "msg": err or fb_err or "图片上传失败"}

        return {
            "ok": True,
            "pid": pid,
            "type": resolved_mime,
            "url": f"https://wx1.sinaimg.cn/bmiddle/{pid}.jpg",
            "large_url": f"https://wx1.sinaimg.cn/large/{pid}.jpg",
            "msg": "上传成功",
        }

    def _prepare_pic_items(
        self,
        images: list[str] | None = None,
        pics: list[dict | str] | None = None,
        dry_run: bool = False,
    ) -> tuple[list[dict], str | None]:
        items: list[dict] = []
        for entry in pics or []:
            if isinstance(entry, str) and entry.strip():
                items.append({"type": "image/jpeg", "pid": entry.strip()})
            elif isinstance(entry, dict) and entry.get("pid"):
                items.append(
                    {
                        "type": entry.get("type") or "image/jpeg",
                        "pid": str(entry["pid"]).strip(),
                    }
                )

        for idx, path in enumerate(images or [], 1):
            if not isinstance(path, str) or not path.strip():
                continue
            path = path.strip()
            if dry_run:
                if not os.path.isfile(path):
                    return [], f"图片文件不存在: {path}"
                items.append({"type": _guess_mime(path), "pid": f"<dry-run-pid-{idx}>"})
            else:
                up = self.upload_image(file_path=path)
                if not up.get("ok"):
                    return [], up.get("msg") or f"图片上传失败: {path}"
                items.append({"type": up["type"], "pid": up["pid"]})

        if len(items) > MAX_IMAGES:
            return [], f"单条微博最多支持 {MAX_IMAGES} 张图片（当前 {len(items)} 张）"
        return items, None

    def _normalize_post_result(self, api_res: dict, default_visible: int) -> dict:
        raw = api_res.get("raw") or {}
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        uid = str(user.get("id") or self._uid or "")
        screen_name = str(user.get("screen_name") or self._screen_name or "")
        mid = str(data.get("idstr") or data.get("id") or data.get("mid") or "")
        mblogid = str(data.get("mblogid") or "")
        vis_obj = data.get("visible")
        vis_type = (
            vis_obj.get("type", default_visible)
            if isinstance(vis_obj, dict)
            else default_visible
        )
        post_url = f"https://weibo.com/{uid}/{mblogid}" if (uid and mblogid) else ""

        return {
            "ok": True,
            "mid": mid,
            "idstr": mid,
            "mblogid": mblogid,
            "url": post_url,
            "created_at": data.get("created_at") or "",
            "text_raw": data.get("text_raw") or data.get("text") or "",
            "visible": vis_type,
            "visible_label": VISIBLE_OPTIONS.get(vis_type, str(vis_type)),
            "user": {"id": uid, "screen_name": screen_name},
            "msg": raw.get("msg") or "发布成功",
            "raw": raw,
        }

    def publish(
        self,
        content: str = "",
        visible: int = 0,
        images: list[str] | None = None,
        pics: list[dict | str] | None = None,
        schedule_time=None,
        topic_id: str | None = None,
        sync_mblog: int = 1,
        share_id: str = "",
        auth_state: int | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Publish a text/image/scheduled Weibo post."""
        try:
            vis = self._validate_visible(visible)
        except ValueError as exc:
            return {"ok": False, "msg": str(exc)}

        text = str(content or "")
        if not text.strip() and not images and not pics:
            return {"ok": False, "msg": "微博正文与图片不能同时为空"}

        schedule_ts = None
        endpoint = "/ajax/statuses/update"
        if schedule_time is not None and schedule_time != "":
            try:
                schedule_ts = parse_schedule_timestamp(schedule_time)
            except ValueError as exc:
                return {"ok": False, "msg": str(exc)}
            endpoint = "/ajax/statuses/schedule/upload"

        sess = self.ensure_session()
        if not sess.get("ok"):
            return {"ok": False, "msg": sess.get("message") or "未登录"}

        pic_items, pic_err = self._prepare_pic_items(images=images, pics=pics, dry_run=dry_run)
        if pic_err:
            return {"ok": False, "msg": pic_err}

        form: dict = {
            "content": text,
            "visible": vis,
            "share_id": share_id,
        }
        if pic_items:
            form["pic_id"] = json.dumps(pic_items, ensure_ascii=False)
        if auth_state:
            form["auth_state"] = int(auth_state)
        if topic_id:
            form["topic_id"] = str(topic_id)
            form["sync_mblog"] = 1 if sync_mblog else 0
        if schedule_ts is not None:
            form["schedule_timestamp"] = schedule_ts

        cleaned_payload = _clean_form(form)
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "scheduled": schedule_ts is not None,
                "endpoint": endpoint,
                "payload": cleaned_payload,
                "pics": pic_items,
                "visible": vis,
                "visible_label": VISIBLE_OPTIONS[vis],
                "user": {"id": self._uid, "screen_name": self._screen_name},
                "msg": "干跑校验通过（未实际发布）",
            }

        res = self._post_ajax(endpoint, cleaned_payload)
        if not res.get("ok"):
            return res

        normalized = self._normalize_post_result(res, default_visible=vis)
        normalized["scheduled"] = schedule_ts is not None
        normalized["schedule_timestamp"] = schedule_ts
        normalized["pics"] = pic_items
        if not normalized["text_raw"]:
            normalized["text_raw"] = text
        return normalized

    def check_can_edit(self, mid: str) -> dict:
        """Check via /ajax/statuses/checkCanEdit whether a post can be edited."""
        mid_str = str(mid or "").strip()
        if not mid_str:
            return {"ok": False, "can_edit": False, "msg": "缺少微博 mid"}

        sess = self.ensure_session()
        if not sess.get("ok"):
            return {"ok": False, "can_edit": False, "msg": sess.get("message") or "未登录"}

        self._sync_xsrf_header()
        try:
            resp = self.session.get(
                "https://weibo.com/ajax/statuses/checkCanEdit",
                params={"mid": mid_str},
                timeout=self.timeout,
            )
            js = resp.json()
        except (RequestException, ValueError) as exc:
            return {"ok": False, "can_edit": False, "mid": mid_str, "msg": f"校验可编辑状态失败: {exc}"}

        if js.get("ok") == -100:
            return {"ok": False, "can_edit": False, "mid": mid_str, "msg": js.get("msg") or "登录已失效", "raw": js}

        if not (isinstance(js.get("ok"), (int, float)) and js["ok"] > 0):
            return {
                "ok": False,
                "can_edit": False,
                "mid": mid_str,
                "msg": js.get("tip_message") or js.get("msg") or "当前微博不可编辑",
                "raw": js,
            }

        tip_message = js.get("tip_message") or ""
        tip_type = js.get("tip_type") or ""
        status_obj = js.get("status") if isinstance(js.get("status"), dict) else {}
        edit_cfg = status_obj.get("edit_config") if isinstance(status_obj.get("edit_config"), dict) else {}

        if tip_message:
            return {
                "ok": True,
                "can_edit": False,
                "mid": mid_str,
                "tip_type": tip_type,
                "msg": tip_message,
                "status": status_obj,
                "raw": js,
            }

        if edit_cfg.get("need") and edit_cfg.get("residue_num") == 0:
            return {
                "ok": True,
                "can_edit": False,
                "mid": mid_str,
                "msg": "当前账号暂无剩余免费编辑次数（需会员或编辑权益）",
                "status": status_obj,
                "raw": js,
            }

        return {
            "ok": True,
            "can_edit": True,
            "mid": mid_str,
            "content": status_obj.get("text_raw") or status_obj.get("text") or "",
            "visible": ((status_obj.get("visible") or {}).get("type") if isinstance(status_obj.get("visible"), dict) else None),
            "status": status_obj,
            "msg": "当前微博可编辑",
            "raw": js,
        }

    def edit(
        self,
        mid: str,
        content: str,
        visible: int | None = None,
        images: list[str] | None = None,
        pics: list[dict | str] | None = None,
        check_first: bool = True,
        dry_run: bool = False,
    ) -> dict:
        """Edit an existing Weibo post via /ajax/statuses/modify."""
        mid_str = str(mid or "").strip()
        if not mid_str:
            return {"ok": False, "msg": "缺少微博 mid"}

        text = str(content or "")
        if not text.strip() and not images and not pics:
            return {"ok": False, "msg": "编辑后的正文与图片不能同时为空"}

        vis = None
        if visible is not None and visible != "":
            try:
                vis = self._validate_visible(visible)
            except ValueError as exc:
                return {"ok": False, "msg": str(exc)}

        sess = self.ensure_session()
        if not sess.get("ok"):
            return {"ok": False, "msg": sess.get("message") or "未登录"}

        if check_first and not dry_run:
            chk = self.check_can_edit(mid_str)
            if not chk.get("can_edit"):
                return {
                    "ok": False,
                    "can_edit": False,
                    "mid": mid_str,
                    "msg": chk.get("msg") or "当前微博不可编辑",
                    "raw": chk.get("raw"),
                }

        pic_items, pic_err = self._prepare_pic_items(images=images, pics=pics, dry_run=dry_run)
        if pic_err:
            return {"ok": False, "msg": pic_err}

        form: dict = {"mid": mid_str, "content": text}
        if vis is not None:
            form["visible"] = vis
        if pic_items:
            form["pic_id"] = json.dumps(pic_items, ensure_ascii=False)

        cleaned = _clean_form(form)
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "endpoint": "/ajax/statuses/modify",
                "payload": cleaned,
                "mid": mid_str,
                "msg": "编辑干跑校验通过（未实际提交）",
            }

        res = self._post_ajax("/ajax/statuses/modify", cleaned)
        if not res.get("ok"):
            return res

        normalized = self._normalize_post_result(res, default_visible=vis if vis is not None else 0)
        if not normalized["mid"]:
            normalized["mid"] = mid_str
            normalized["idstr"] = mid_str
        if not normalized["text_raw"]:
            normalized["text_raw"] = text
        if normalized["msg"] == "发布成功" and res.get("raw", {}).get("msg"):
            normalized["msg"] = res["raw"]["msg"]
        elif normalized["msg"] == "发布成功":
            normalized["msg"] = "编辑成功"
        return normalized

    def modify_visibility(self, mid: str, visible: int) -> dict:
        """Change post visibility via /ajax/statuses/modifyVisible (ids, visible)."""
        mid_str = str(mid or "").strip()
        if not mid_str:
            return {"ok": False, "msg": "缺少微博 mid"}

        try:
            vis = self._validate_visible(visible)
        except ValueError as exc:
            return {"ok": False, "msg": str(exc)}

        sess = self.ensure_session()
        if not sess.get("ok"):
            return {"ok": False, "msg": sess.get("message") or "未登录"}

        res = self._post_ajax("/ajax/statuses/modifyVisible", {"ids": mid_str, "visible": vis})
        if not res.get("ok"):
            return res

        raw = res.get("raw") or {}
        statuses = raw.get("statuses") if isinstance(raw.get("statuses"), list) else []
        first = statuses[0] if statuses and isinstance(statuses[0], dict) else {}
        vis_obj = first.get("visible") if isinstance(first.get("visible"), dict) else {}
        actual_vis = vis_obj.get("type", vis)

        return {
            "ok": True,
            "mid": mid_str,
            "visible": actual_vis,
            "visible_label": VISIBLE_OPTIONS.get(actual_vis, str(actual_vis)),
            "edit_count": first.get("edit_count"),
            "msg": raw.get("msg") or "修改可见范围成功",
            "raw": raw,
        }

    def delete(self, mid: str) -> dict:
        """Delete a post via /ajax/statuses/destroy (id)."""
        mid_str = str(mid or "").strip()
        if not mid_str:
            return {"ok": False, "msg": "缺少微博 mid"}

        sess = self.ensure_session()
        if not sess.get("ok"):
            return {"ok": False, "msg": sess.get("message") or "未登录"}

        res = self._post_ajax("/ajax/statuses/destroy", {"id": mid_str})
        if not res.get("ok"):
            return res

        raw = res.get("raw") or {}
        return {
            "ok": True,
            "mid": mid_str,
            "msg": raw.get("msg") or "删除成功",
            "raw": raw,
        }

    def list_my_posts(self, page: int = 1, feature: int = 0) -> dict:
        """Fetch current user's timeline posts via GET /ajax/statuses/mymblog."""
        sess = self.ensure_session()
        if not sess.get("ok"):
            return {"ok": False, "items": [], "msg": sess.get("message") or "未登录"}

        if not self._uid:
            return {"ok": False, "items": [], "msg": "未能获取到当前登录账号 UID"}

        self._sync_xsrf_header()
        try:
            resp = self.session.get(
                "https://weibo.com/ajax/statuses/mymblog",
                params={"uid": self._uid, "page": int(page), "feature": int(feature)},
                timeout=self.timeout,
            )
            js = resp.json()
        except (RequestException, ValueError) as exc:
            return {"ok": False, "items": [], "msg": f"获取个人微博列表失败: {exc}"}

        if not (isinstance(js.get("ok"), (int, float)) and js["ok"] > 0):
            return {
                "ok": False,
                "items": [],
                "msg": js.get("msg") or f"获取微博列表失败 (ok={js.get('ok')})",
                "raw": js,
            }

        raw_list = ((js.get("data") or {}).get("list")) or []
        items = []
        for post in raw_list:
            if not isinstance(post, dict):
                continue
            vis_obj = post.get("visible") if isinstance(post.get("visible"), dict) else {}
            vis_type = vis_obj.get("type", 0)
            mid = str(post.get("idstr") or post.get("id") or post.get("mid") or "")
            mblogid = str(post.get("mblogid") or "")
            pic_ids = post.get("pic_ids") if isinstance(post.get("pic_ids"), list) else []
            pic_infos = post.get("pic_infos") if isinstance(post.get("pic_infos"), dict) else {}
            pics = []
            for pid in pic_ids:
                info = pic_infos.get(pid) or {}
                thumb_raw = (
                    (info.get("bmiddle") or {}).get("url")
                    or (info.get("thumbnail") or {}).get("url")
                    or (info.get("large") or {}).get("url")
                    or f"https://wx1.sinaimg.cn/bmiddle/{pid}.jpg"
                )
                large_raw = (
                    (info.get("large") or {}).get("url")
                    or (info.get("mw2000") or {}).get("url")
                    or (info.get("original") or {}).get("url")
                    or f"https://wx1.sinaimg.cn/large/{pid}.jpg"
                )
                pics.append(
                    {
                        "pid": pid,
                        "url": normalize_weibo_image_url(thumb_raw),
                        "large_url": normalize_weibo_image_url(large_raw),
                    }
                )
            items.append(
                {
                    "mid": mid,
                    "mblogid": mblogid,
                    "created_at": post.get("created_at") or "",
                    "text_raw": post.get("text_raw") or post.get("text") or "",
                    "visible_type": vis_type,
                    "visible_label": VISIBLE_OPTIONS.get(vis_type, str(vis_type)),
                    "pics": pics,
                    "pic_ids": pic_ids,
                    "edit_count": post.get("edit_count") or 0,
                    "attitudes_count": post.get("attitudes_count") or 0,
                    "comments_count": post.get("comments_count") or 0,
                    "reposts_count": post.get("reposts_count") or 0,
                    "url": f"https://weibo.com/{self._uid}/{mblogid}" if (self._uid and mblogid) else "",
                }
            )

        return {
            "ok": True,
            "uid": self._uid,
            "screen_name": self._screen_name,
            "page": int(page),
            "items": items,
            "total": len(items),
            "msg": "获取成功",
        }
