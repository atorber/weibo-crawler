"""HTTP 请求辅助。

- ``random_headers``：防封禁请求头（UA/Accept-Language 每轮固定，Referer 指向用户主页）；
- ``client_hints``：按 UA 生成匹配的 ``sec-ch-ua*``（Firefox/Safari 不发送）；
- ``fetch_json``：统一 JSON 请求（带异常兜底，返回 (json, status)）。

只做纯逻辑，不持有 session；session/配置由调用方传入。
"""

from __future__ import annotations

import random
import re

from requests.exceptions import RequestException

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
]
DEFAULT_ACCEPT_LANGUAGES = ["zh-CN,zh;q=0.9,en;q=0.8"]
DEFAULT_REFERER = "https://m.weibo.cn/"

# API XHR 头：用 cors/empty，避免 navigate + upgrade-insecure-requests
# 被当成页面导航而返回 text/html 风控壳。
_FIXED_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "cache-control": "no-cache",
    "priority": "u=1, i",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest",
    "mweibo-pwa": "1",
}


def pick_session_value(options, fallback, rng: random.Random | None = None) -> str:
    """从候选列表中选一个值（每轮运行只选一次，避免同一 Cookie 下频繁切换指纹）。"""
    chooser = rng or random
    candidates = [str(v) for v in (options or []) if str(v or "").strip()]
    return chooser.choice(candidates or list(fallback))


def _ua_platform(user_agent: str) -> str:
    if "Windows" in user_agent:
        return "Windows"
    if "Android" in user_agent:
        return "Android"
    if "iPhone" in user_agent or "iPad" in user_agent:
        return "iOS"
    if "Macintosh" in user_agent or "Mac OS X" in user_agent:
        return "macOS"
    if "Linux" in user_agent:
        return "Linux"
    return ""


def client_hints(user_agent: str) -> dict:
    """返回与 UA 匹配的 ``sec-ch-ua*``；非 Chromium 内核返回空 dict（真实浏览器也不发）。"""
    ua = user_agent or ""
    edge = re.search(r"Edg(?:A|iOS)?/(\d+)", ua)
    chrome = re.search(r"Chrome/(\d+)", ua)
    if "Firefox/" in ua or not chrome or "CriOS/" in ua:
        return {}
    major = chrome.group(1)
    if edge:
        brands = (
            f'"Chromium";v="{major}", "Microsoft Edge";v="{edge.group(1)}", '
            '"Not.A/Brand";v="99"'
        )
    else:
        brands = (
            f'"Chromium";v="{major}", "Google Chrome";v="{major}", '
            '"Not.A/Brand";v="99"'
        )
    hints = {
        "sec-ch-ua": brands,
        "sec-ch-ua-mobile": "?1" if "Mobile" in ua else "?0",
    }
    platform = _ua_platform(ua)
    if platform:
        hints["sec-ch-ua-platform"] = f'"{platform}"'
    return hints


def apply_user_agent(headers: dict, user_agent: str) -> dict:
    """把 UA 及匹配的 client hints 写入 headers（移除不匹配的旧 hints）。"""
    for key in list(headers):
        if key.lower().startswith("sec-ch-ua") or key.lower() == "user-agent":
            headers.pop(key)
    headers["user-agent"] = user_agent
    headers.update(client_hints(user_agent))
    return headers


def profile_referer(user_id) -> str:
    uid = str(user_id or "").strip()
    return f"https://m.weibo.cn/u/{uid}" if uid else DEFAULT_REFERER


def random_headers(
    enabled: bool,
    anti_ban_config: dict | None,
    fallback_headers: dict,
    rng: random.Random | None = None,
    *,
    user_agent: str | None = None,
    accept_language: str | None = None,
    referer: str | None = None,
    xsrf_token: str | None = None,
) -> dict:
    """返回 API 请求头：关闭防封禁时原样返回 fallback。

    UA / Accept-Language 由调用方按「每轮运行一次」选定后传入；未传入时才从配置随机选。
    """
    if not enabled:
        return fallback_headers
    config = anti_ban_config or {}
    ua = user_agent or pick_session_value(
        config.get("user_agents"), DEFAULT_USER_AGENTS, rng
    )
    language = accept_language or pick_session_value(
        config.get("accept_languages"), DEFAULT_ACCEPT_LANGUAGES, rng
    )
    headers = dict(_FIXED_HEADERS)
    headers["Referer"] = referer or DEFAULT_REFERER
    headers["accept-language"] = language
    if xsrf_token:
        headers["x-xsrf-token"] = xsrf_token
    return apply_user_agent(headers, ua)


def fetch_json(
    session,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    logger=None,
    timeout: int = 10,
) -> tuple[dict, int]:
    ""
    try:
        response = session.get(
            url, params=params, headers=headers, verify=False, timeout=timeout
        )
        response.raise_for_status()
        return response.json(), response.status_code
    except RequestException as exc:
        if logger is not None:
            logger.error("请求失败，错误信息：%s", exc)
        return {}, 500
    except ValueError as exc:
        if logger is not None:
            logger.error("JSON 解码失败，错误信息：%s", exc)
        return {}, 500
