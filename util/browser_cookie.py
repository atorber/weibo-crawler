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

logger = logging.getLogger("weibo.cookie")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + os.sep
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_CONFIG_PATH = os.path.join(BASE_DIR, "config.json.example")

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

    # 1. 探针 1：测试微博网页端 (weibo.com PC)
    headers_pc = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cookie": cookie_str,
        "Referer": "https://weibo.com/",
        "accept": "application/json, text/plain, */*",
    }
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

    # 2. 探针 2：测试微博移动端 (m.weibo.cn H5)
    headers_mobile = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        ),
        "Cookie": cookie_str,
        "Referer": "https://m.weibo.cn/",
        "accept": "application/json, text/plain, */*",
    }
    try:
        r_mob = requests.get(
            "https://m.weibo.cn/api/config",
            headers=headers_mobile,
            timeout=6,
        )
        if r_mob.status_code == 200:
            js = r_mob.json()
            if js.get("data", {}).get("login") is True:
                user = js.get("data", {}).get("user", {})
                s_name = user.get("screen_name", "已登录用户")
                return {
                    "valid": True,
                    "personal_login": True,
                    "message": f"移动端 Cookie 验证通过！登录账号：{s_name}",
                    "user": {"id": user.get("id", ""), "screen_name": s_name},
                }
    except Exception as e:
        logger.debug(f"Mobile probe failed: {e}")

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
                "message": "Cookie 连通性测试通过（具备微博公共数据抓取权限，未绑定个人账号画像）",
                "user": {"id": "", "screen_name": "有效凭证 (公共抓取)"},
            }
    except Exception as e:
        logger.debug(f"Public probe failed: {e}")

    return {
        "valid": False,
        "personal_login": False,
        "message": "Cookie 认证未通过或已过期，未能获取到有效数据权限，建议重新登录并更新 Cookie",
        "user": {},
    }


def extract_browser_cookies(browser_name="auto"):
    """通过 rookiepy 从本地浏览器自动提取微博 Cookie."""
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
            if res["has_sub"]:
                return res["cookie_str"], None, res["browser_name"]
            results.append(res)
        elif err and "未安装" not in err and "未找到" not in err:
            errors.append(err)

    if results:
        best = max(results, key=lambda x: x["count"])
        return best["cookie_str"], None, best["browser_name"]

    msg = "未能自动从本地浏览器中提取到微博 Cookie。"
    if errors:
        msg += " 失败提示: " + "；".join(errors[:2])
    else:
        msg += " 请确保已在 Chrome / Edge / Firefox 等浏览器登录过 weibo.com。"
    return None, msg, None


def extract_and_save_cookie(browser_name="auto", cookie_file_path=None):
    """Extracts cookie from browser, verifies it, and persists to config.json (and optional cookie_file_path).

    Returns:
        dict: {
            "success": bool,
            "cookie": str or None,
            "browser": str or None,
            "valid": bool,
            "user": dict,
            "message": str,
            "timestamp": str
        }
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cookie_str, err_msg, detected_browser = extract_browser_cookies(
        browser_name
    )
    if err_msg or not cookie_str:
        return {
            "success": False,
            "cookie": None,
            "browser": detected_browser or browser_name,
            "valid": False,
            "user": {},
            "message": err_msg or "未能从浏览器提取到有效微博 Cookie",
            "timestamp": now_str,
        }

    check_result = verify_cookie_string(cookie_str)
    valid = check_result.get("valid", False)

    # Save to config.json if valid
    if valid:
        try:
            parsed = _read_parsed_config()
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

    return {
        "success": True,
        "cookie": cookie_str,
        "browser": detected_browser or browser_name,
        "valid": valid,
        "user": check_result.get("user", {}),
        "message": (
            f"成功从 {detected_browser or browser_name} 提取微博 Cookie！"
            + (
                f" {check_result.get('message', '')}"
                if check_result.get("message")
                else ""
            )
        ),
        "timestamp": now_str,
    }
