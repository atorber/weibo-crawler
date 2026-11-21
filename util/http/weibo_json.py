"""微博 JSON 请求与解析。

``get_weibo_json`` 负责请求第 N 页接口、处理验证码/空数据/网络异常/HTML 风控页，
并返回解析后的 JSON；依赖的 wb 属性/方法（session/headers/crawl_success 等）由
Weibo 实例提供。

返回约定：
- ``dict`` 且含 data：成功；
- ``None``：分页自然结束；
- ``{}``：本页硬失败（重试耗尽）；
- ``"html_risk"``：拿到 HTML 风控页（且刷新 Cookie 无效），上层应冷却后重试同页。
"""

from __future__ import annotations

import logging
import random

from requests.exceptions import RequestException

from util.http import rate_limit

logger = logging.getLogger("weibo")

# 上层可识别的风控哨兵（get_one_page → need_rest）
HTML_RISK = "html_risk"


def _sleep(seconds):
    from weibo import sleep as weibo_sleep

    weibo_sleep(seconds)


def _is_json_decode_error(exc: BaseException) -> bool:
    """兼容 requests 真库与测试 stub（stub 可能没有 JSONDecodeError 符号）。"""
    if type(exc).__name__ == "JSONDecodeError":
        return True
    return isinstance(exc, ValueError) and "Expecting value" in str(exc)


def _response_text(response) -> str:
    text = getattr(response, "text", None)
    if text is not None:
        return text
    try:
        raw = getattr(response, "content", b"") or b""
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _response_diag(response) -> str:
    """把 status / Content-Type / body 摘要打进日志，避免只看到 JSONDecodeError。"""
    if response is None:
        return "无响应对象"
    status = getattr(response, "status_code", "?")
    headers = getattr(response, "headers", {}) or {}
    ctype = headers.get("Content-Type") or headers.get("content-type") or "?"
    body = (_response_text(response) or "").strip()
    preview = body[:120].replace("\n", "\\n") if body else "<empty>"
    return (
        f"status={status} content_type={ctype} "
        f"body_len={len(body)} body_preview={preview!r}"
    )


def looks_like_html_risk(response) -> bool:
    """判断响应是否为 HTML 风控/验证壳（而非 API JSON）。"""
    if response is None:
        return False
    headers = getattr(response, "headers", {}) or {}
    ctype = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    if "text/html" in ctype:
        return True
    head = (_response_text(response) or "").lstrip()[:64].lower()
    return head.startswith(("<!doctype", "<html", "<head"))


def _anti_ban_cfg(wb) -> dict:
    return getattr(wb, "anti_ban_config", None) or {}


def _html_risk_cooldown(wb, attempt: int) -> int:
    """HTML 风控冷却：明显长于普通网络重试（默认 120→240→360，上限可配）。"""
    cfg = _anti_ban_cfg(wb)
    base = int(cfg.get("html_risk_cooldown", 120) or 120)
    cap = int(cfg.get("html_risk_cooldown_max", 600) or 600)
    # attempt 从 0 起：base / 2*base / 3*base ...
    seconds = int(base * (attempt + 1))
    seconds = min(max(seconds, base), cap)
    # 轻微抖动，避免固定节奏
    return int(seconds * random.uniform(0.9, 1.1))


def _network_backoff(attempt: int, backoff_factor: int = 5) -> int:
    return min(30, backoff_factor * (2 ** (attempt + 1)))


def record_html_risk(wb) -> None:
    """登记一次 HTML 风控命中（计入连续错误与本轮统计）。"""
    wb.update_crawl_stats(api_error=True)
    crawl_success = getattr(wb, "crawl_success", None)
    if isinstance(crawl_success, dict):
        crawl_success["html_risk"] = True
        crawl_success["html_risk_hits"] = int(crawl_success.get("html_risk_hits") or 0) + 1


def _handle_html_risk(wb, page, response, attempt: int) -> bool:
    """记录风控；首次命中尝试刷新 Cookie。返回是否刷新成功（成功则值得立即重试）。

    请求层不再长时间冷却重试：同一会话继续请求只会加重风控，冷却交给分页层统一处理。
    """
    logger.warning(
        "第%d页疑似风控：接口返回 HTML 而非 JSON（%s）",
        page,
        _response_diag(response),
    )
    record_html_risk(wb)
    refresher = getattr(wb, "try_auto_refresh_cookie", None)
    if attempt == 0 and callable(refresher):
        return bool(refresher("HTML风控页"))
    return False


def get_weibo_json(wb, page) -> object:
    """获取网页中微博json数据"""
    url = "https://m.weibo.cn/api/container/getIndex?"
    params = (
        {
            "container_ext": "profile_uid:" + str(wb.user_config["user_id"]),
            "containerid": "100103type=401&q=" + wb.query,
            "page_type": "searchall",
        }
        if wb.query
        else {"containerid": "230413" + str(wb.user_config["user_id"])}
    )
    params["page"] = page
    params["count"] = wb.page_weibo_count
    # 重试与退避：最多重试 3 次。普通网络错误短退避；HTML 风控用长冷却。
    max_retries = 3
    retries = 0
    html_risk_hits = 0

    while retries < max_retries:
        response = None
        try:
            # 防封禁：本轮固定指纹的 API 请求头
            current_headers = wb.get_random_headers()

            # 防封禁：统一节奏（与详情页/用户信息共用上次请求时刻）
            waited = rate_limit.pace(wb, wb.calculate_dynamic_delay(), _sleep)
            if waited > 0:
                logger.debug(f"请求间隔: {waited:.1f} 秒")

            response = wb.session.get(
                url, params=params, headers=current_headers, timeout=10
            )
            if getattr(response, "status_code", 200) in (403, 418, 432):
                refresher = getattr(wb, "try_auto_refresh_cookie", None)
                if callable(refresher) and refresher(f"HTTP {response.status_code}"):
                    continue

            # 先识别 HTML 风控页，避免丢进 JSONDecodeError 短退避空转
            if looks_like_html_risk(response):
                refreshed = _handle_html_risk(wb, page, response, html_risk_hits)
                html_risk_hits += 1
                retries += 1
                if refreshed:
                    continue
                break

            response.raise_for_status()  # 如果响应状态码不是 200，会抛出 HTTPError
            js = response.json()

            # 更新统计：成功请求
            wb.update_crawl_stats(request_count=1)

            if "data" in js:
                logger.info(f"成功获取到页面 {page} 的数据。")
                return js

            # 无 data 的响应分两种，不能再一律当验证码并 sys.exit：
            # 1) 带 url：验证码挑战，交 handle_captcha 处理；
            # 2) 不带 url：分页自然结束（典型 {"ok":0,"msg":"这里还没有内容"}），
            #    返回 None 作为「无更多数据」哨兵，由 get_one_page 置 api_ended。
            if js.get("url"):
                logger.warning("未能获取到数据，检测到验证码挑战。")
                if wb.handle_captcha(js):
                    logger.info("用户已完成验证码验证，继续请求数据。")
                    retries = 0  # 重置重试计数器
                    continue
                logger.error("验证码验证失败或未完成，跳过当前页面。")
                return {}
            logger.info(
                "第%d页接口无更多数据（%s），视为分页结束。",
                page,
                js.get("msg") or "无 data 字段",
            )
            return None
        except RequestException as e:
            retries += 1
            # JSONDecodeError 且响应是 HTML：交上层冷却
            if _is_json_decode_error(e) and looks_like_html_risk(response):
                refreshed = _handle_html_risk(wb, page, response, html_risk_hits)
                html_risk_hits += 1
                if refreshed:
                    continue
                break
            sleep_time = _network_backoff(retries - 1)
            kind = "JSON 解码失败" if _is_json_decode_error(e) else "请求失败"
            logger.error(
                "第%d页%s：%s；%s。等待 %s 秒后重试...",
                page,
                kind,
                e,
                _response_diag(response),
                sleep_time,
            )
            _sleep(sleep_time)
            wb.update_crawl_stats(api_error=True)
        except ValueError as ve:
            retries += 1
            if looks_like_html_risk(response):
                refreshed = _handle_html_risk(wb, page, response, html_risk_hits)
                html_risk_hits += 1
                if refreshed:
                    continue
                break
            sleep_time = _network_backoff(retries - 1)
            logger.error(
                "第%d页 JSON 解码失败：%s；%s。等待 %s 秒后重试...",
                page,
                ve,
                _response_diag(response),
                sleep_time,
            )
            _sleep(sleep_time)
            wb.update_crawl_stats(api_error=True)

    if html_risk_hits > 0:
        logger.error(
            "第%d页命中 HTML 风控（%d 次），交上层冷却后重试同页。",
            page,
            html_risk_hits,
        )
        return HTML_RISK

    logger.error("超过最大重试次数，跳过当前页面（page=%s）。", page)
    return {}
