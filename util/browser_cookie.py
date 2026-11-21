#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Browser Cookie Extraction & Verification Utility.

Shared by both the Web Console API (service.py) and the Crawler process (weibo.py)
for one-click extraction, periodic background syncing, and on-expiration hot-reload.
"""

from datetime import datetime
import json
import logging
import os
import re

try:
    import json5
except ImportError:
    json5 = None
import requests

from util.config import config_paths

logger = logging.getLogger("weibo.cookie")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CONFIG_PATH, EXAMPLE_CONFIG_PATH = config_paths.config_files(BASE_DIR)

DEFAULT_COOKIE_AUTO_CONFIG = {
    "enabled": False,
    "browser": "auto",
    "refresh_on_expire": True,
    "check_before_start": True,
    "interval_minutes": 360,
}


def get_cookie_auto_config(parsed_config=None):
    """Returns normalized cookie_auto_config dictionary."""
    if parsed_config is None:
        parsed_config = _read_parsed_config()
    raw_auto = parsed_config.get("cookie_auto_config")
    if not isinstance(raw_auto, dict):
        raw_auto = {}
    merged = dict(DEFAULT_COOKIE_AUTO_CONFIG)
    merged.update(raw_auto)
    merged["enabled"] = bool(merged.get("enabled", False))
    merged["browser"] = str(merged.get("browser", "auto") or "auto").strip()
    merged["refresh_on_expire"] = bool(merged.get("refresh_on_expire", True))
    merged["check_before_start"] = bool(merged.get("check_before_start", True))
    try:
        merged["interval_minutes"] = max(0, int(merged.get("interval_minutes", 360)))
    except (ValueError, TypeError):
        merged["interval_minutes"] = 360
    return merged


def _read_parsed_config():
    target_path = (
        CONFIG_PATH if os.path.isfile(CONFIG_PATH) else EXAMPLE_CONFIG_PATH
    )
    if not os.path.isfile(target_path):
        return {}
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            return json5.loads(content)
        except Exception:
            return json.loads(content)
    except Exception:
        return {}


def has_login_markers(cookie_dict) -> bool:
    """Cookie 是否带登录态标记（游客 Cookie 只有 tid/SUB/SUBP 等）。"""
    if not isinstance(cookie_dict, dict):
        return False
    if str(cookie_dict.get("MLOGIN") or "") == "1":
        return True
    return any(cookie_dict.get(key) for key in ("SSOLoginState", "ALF", "SCF"))


def verify_cookie_string(cookie_str):
    """Probes Weibo PC, Mobile, and Public endpoints to check if a Cookie string is valid."""
    if not cookie_str or cookie_str.strip() in (
        "your cookie",
        "YOUR_WEIBO_COOKIE_HERE",
    ):
        return {
            "valid": False,
            "personal_login": False,
            "message": "当前未配置 Cookie（处于免登录匿名模式）",
            "user": {},
        }

    headers_pc = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cookie": cookie_str,
        "Referer": "https://weibo.com/",
        "accept": "application/json, text/plain, */*",
    }

    # 1. 探针 1：微博移动端 (m.weibo.cn) 登录标志——爬虫走的就是这个域，结论最可靠
    mobile_login = _probe_mobile_login(cookie_str)
    if mobile_login is not None and mobile_login.get("login"):
        s_name = mobile_login.get("screen_name") or "已登录用户"
        return {
            "valid": True,
            "personal_login": True,
            "message": f"Cookie 验证通过！登录账号：{s_name}",
            "user": {"id": mobile_login.get("uid", ""), "screen_name": s_name},
        }

    # 2. 探针 2：微博网页端 (weibo.com PC)。游客 Cookie 也会返回 ok=1，
    #    所以只在移动端探针请求失败（无法判断）时才用它判定登录
    pc_result = None if mobile_login is not None else _probe_pc_login(headers_pc)
    if pc_result is not None:
        return pc_result

    # 3. 探针 3：测试公共只读抓取权限（针对访客 Cookie 或 SUB 凭据）
    try:
        r_pub = requests.get(
            "https://weibo.com/ajax/profile/info?custom=1669879400",
            headers=headers_pc,
            timeout=6,
        )
        if r_pub.status_code == 200 and r_pub.json().get("ok") == 1:
            return {
                "valid": True,
                "personal_login": False,
                "message": (
                    "Cookie 未登录（游客身份）：只能读取公开数据，爬虫翻页会被微博风控；"
                    "请在浏览器登录 m.weibo.cn 后重新提取 Cookie"
                ),
                "user": {"id": "", "screen_name": "游客 (未登录)"},
            }
    except Exception as e:
        logger.debug(f"Public probe failed: {e}")

    return {
        "valid": False,
        "personal_login": False,
        "message": "Cookie 认证未通过或已过期，未能获取到有效数据权限，建议重新登录并更新 Cookie",
        "user": {},
    }


def _probe_mobile_login(cookie_str):
    """请求 m.weibo.cn/api/config；返回 {"login", "uid", "screen_name"}，请求失败返回 None。"""
    headers_mobile = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        ),
        "Cookie": cookie_str,
        "Referer": "https://m.weibo.cn/",
        "accept": "application/json, text/plain, */*",
        "x-requested-with": "XMLHttpRequest",
        "mweibo-pwa": "1",
    }
    try:
        r_mob = requests.get(
            "https://m.weibo.cn/api/config",
            headers=headers_mobile,
            timeout=6,
        )
        if r_mob.status_code != 200:
            return None
        data = (r_mob.json() or {}).get("data") or {}
    except Exception as e:
        logger.debug(f"Mobile probe failed: {e}")
        return None
    user = data.get("user") or {}
    return {
        "login": data.get("login") is True,
        "uid": str(data.get("uid") or user.get("id") or ""),
        "screen_name": user.get("screen_name", ""),
    }


def _probe_pc_login(headers_pc):
    """weibo.com 网页端探针（仅移动端探针不可用时兜底）；通过返回结果 dict，否则 None。"""
    try:
        r_pc = requests.get(
            "https://weibo.com/ajax/profile/detail",
            headers=headers_pc,
            timeout=6,
        )
        if r_pc.status_code == 200:
            js = r_pc.json()
            if js.get("ok") == 1:
                data_pc = js.get("data", {})
                verified_url = data_pc.get("verified_url", "")
                m = re.search(r"uid=(\d+)", verified_url)
                uid = m.group(1) if m else ""
                screen_name = ""
                ip_location = data_pc.get("ip_location", "")
                if uid:
                    try:
                        r_u = requests.get(
                            f"https://weibo.com/ajax/profile/info?uid={uid}",
                            headers=headers_pc,
                            timeout=5,
                        )
                        if r_u.status_code == 200:
                            u_info = (
                                r_u.json().get("data", {}).get("user", {})
                            )
                            screen_name = u_info.get("screen_name", "")
                    except Exception:
                        pass
                name_display = screen_name or (
                    f"UID: {uid}" if uid else "已登录用户"
                )
                loc_display = f" ({ip_location})" if ip_location else ""
                return {
                    "valid": True,
                    "personal_login": True,
                    "message": f"Cookie 验证通过！登录账号：{name_display}{loc_display}",
                    "user": {"id": uid, "screen_name": name_display},
                }
    except Exception as e:
        logger.debug(f"PC probe failed: {e}")
    return None


def extract_browser_cookies(browser_name="auto", prefer_domain=None):
    """通过 rookiepy 从本地浏览器自动提取微博 Cookie.

    Args:
        browser_name: 浏览器标识或 ``"auto"``.
        prefer_domain: 同名 Cookie 冲突时的优先域（默认 ``"weibo.cn"`` 优先以兼容爬虫；
            发布场景可传 ``"weibo.com"`` 使 ``weibo.com`` 域 Cookie 覆盖同名键）。
    """
    try:
        import rookiepy
    except ImportError:
        return (
            None,
            "未安装 rookiepy 库，请先在终端运行 pip install rookiepy",
            None,
        )

    browser_map = {
        "chrome": ("Google Chrome", getattr(rookiepy, "chrome", None)),
        "edge": ("Microsoft Edge", getattr(rookiepy, "edge", None)),
        "firefox": ("Mozilla Firefox", getattr(rookiepy, "firefox", None)),
        "safari": ("Apple Safari", getattr(rookiepy, "safari", None)),
        "brave": ("Brave", getattr(rookiepy, "brave", None)),
        "arc": ("Arc", getattr(rookiepy, "arc", None)),
        "opera": ("Opera", getattr(rookiepy, "opera", None)),
        "chromium": ("Chromium", getattr(rookiepy, "chromium", None)),
        "vivaldi": ("Vivaldi", getattr(rookiepy, "vivaldi", None)),
    }

    domains = ["weibo.com", "weibo.cn"]

    def try_extract_from(b_key):
        b_info = browser_map.get(b_key)
        if not b_info or not b_info[1]:
            return None, f"当前环境暂不支持或未找到 {b_key} 提取接口"
        b_name, fn = b_info
        try:
            raw_cookies = fn(domains)
            if not raw_cookies:
                return None, f"{b_name} 中未找到微博登录 Cookie"

            def priority(c):
                dom = c.get("domain", "")
                if "visitor" in dom:
                    return 0
                if prefer_domain == "weibo.com":
                    if dom.endswith("weibo.cn"):
                        return 1
                    if dom.endswith("weibo.com"):
                        return 2
                else:
                    if dom.endswith("weibo.com"):
                        return 1
                    if dom.endswith("weibo.cn"):
                        return 2
                return 0

            sorted_cookies = sorted(raw_cookies, key=priority)
            cookie_dict = {}
            has_sub = False
            for c in sorted_cookies:
                name = c.get("name")
                val = c.get("value")
                if name and val is not None:
                    cookie_dict[name] = val
                    if name == "SUB":
                        has_sub = True

            cookie_str = "; ".join(
                [f"{k}={v}" for k, v in cookie_dict.items()]
            )
            return {
                "cookie_str": cookie_str,
                "browser_key": b_key,
                "browser_name": b_name,
                "count": len(cookie_dict),
                "has_sub": has_sub,
                "has_login": has_login_markers(cookie_dict),
            }, None
        except Exception as e:
            err_msg = str(e)
            if (
                "Operation not permitted" in err_msg
                or "Full Disk Access" in err_msg
            ):
                return (
                    None,
                    f"{b_name} 读取受限（macOS 安全策略需要授予终端完全磁盘访问权限）",
                )
            if (
                "Can't find cookies file" in err_msg
                or "can't find" in err_msg.lower()
            ):
                return (
                    None,
                    f"{b_name} 未找到 Cookie 数据文件（未安装或未产生数据）",
                )
            return None, f"{b_name} 读取异常: {err_msg}"

    if browser_name and browser_name != "auto":
        res, err = try_extract_from(browser_name)
        if err:
            return None, err, browser_name
        return res["cookie_str"], None, res["browser_name"]

    # 自动探测模式
    candidates = [
        "chrome",
        "edge",
        "firefox",
        "brave",
        "arc",
        "safari",
        "opera",
        "chromium",
    ]
    results = []
    errors = []
    for b in candidates:
        res, err = try_extract_from(b)
        if res:
            if res["has_sub"] and res.get("has_login"):
                return res["cookie_str"], None, res["browser_name"]
            results.append(res)
        elif err and "未安装" not in err and "未找到" not in err:
            errors.append(err)

    if results:
        # 没有带登录标记的浏览器时，退而求其次：有 SUB 的优先，其次字段最多的
        best = max(results, key=lambda x: (x["has_sub"], x["count"]))
        return best["cookie_str"], None, best["browser_name"]

    msg = "未能自动从本地浏览器中提取到微博 Cookie。"
    if errors:
        msg += " 失败提示: " + "；".join(errors[:2])
    else:
        msg += " 请确保已在 Chrome / Edge / Firefox 等浏览器登录过 weibo.com。"
    return None, msg, None


def extract_and_save_cookie(
    browser_name="auto",
    cookie_file_path=None,
    prefer_domain=None,
    browser=None,
):
    """Extracts cookie from browser, verifies it, and persists to config.json (and optional cookie_file_path).

    Returns:
        dict: {
            "ok": bool,
            "success": bool,
            "cookie": str or None,
            "browser": str or None,
            "valid": bool,
            "user": dict,
            "message": str,
            "timestamp": str
        }
    """
    target_browser = browser if browser is not None else browser_name
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cookie_str, err_msg, detected_browser = extract_browser_cookies(
        target_browser, prefer_domain=prefer_domain
    )
    if err_msg or not cookie_str:
        return {
            "ok": False,
            "success": False,
            "cookie": None,
            "browser": detected_browser or target_browser,
            "valid": False,
            "user": {},
            "message": err_msg or "未能从浏览器提取到有效微博 Cookie",
            "timestamp": now_str,
        }

    check_result = verify_cookie_string(cookie_str)
    valid = check_result.get("valid", False)
    personal_login = bool(check_result.get("personal_login"))
    parsed = None
    try:
        parsed = _read_parsed_config()
    except Exception as e:
        logger.debug(f"读取配置失败: {e}")
    # 游客 Cookie 只在配置里本来没有 Cookie 时写入，绝不覆盖已有 Cookie
    # （浏览器未登录时提取到的是游客 SUB，覆盖后爬虫翻页会持续被风控）
    current_cookie = str((parsed or {}).get("cookie") or "").strip()
    has_current = bool(current_cookie) and current_cookie not in (
        "your cookie",
        "YOUR_WEIBO_COOKIE_HERE",
    )
    should_save = valid and (personal_login or not has_current)
    skipped_guest = valid and not personal_login and has_current

    if should_save:
        try:
            if parsed:
                # If config["cookie"] points to a .txt file, update that file; otherwise update config["cookie"]
                cfg_cookie = parsed.get("cookie", "")
                if (
                    isinstance(cfg_cookie, str)
                    and cfg_cookie.endswith(".txt")
                ) or cookie_file_path:
                    target_txt = cookie_file_path or cfg_cookie
                    if not os.path.isabs(target_txt):
                        target_txt = os.path.join(BASE_DIR, target_txt)
                    with open(target_txt, "w", encoding="utf-8") as f:
                        f.write(cookie_str)
                else:
                    parsed["cookie"] = cookie_str
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                        f.write(
                            json.dumps(parsed, indent=4, ensure_ascii=False)
                        )
        except Exception as e:
            logger.error(f"自动保存提取的 Cookie 到配置文件失败: {e}")

    message = f"成功从 {detected_browser or target_browser} 提取微博 Cookie！" + (
        f" {check_result.get('message', '')}" if check_result.get("message") else ""
    )
    if skipped_guest:
        message = (
            f"{detected_browser or target_browser} 中的微博 Cookie 未登录（游客身份），"
            "未覆盖配置中的 Cookie；请先在浏览器登录 m.weibo.cn / weibo.com"
        )
    return {
        "ok": bool(valid),
        "success": not skipped_guest,
        "cookie": cookie_str,
        "browser": detected_browser or target_browser,
        "valid": valid and not skipped_guest,
        "personal_login": personal_login,
        "saved": should_save,
        "user": check_result.get("user", {}),
        "message": message,
        "timestamp": now_str,
    }
