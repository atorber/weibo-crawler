"""统一请求节奏。

所有发往微博的请求（列表页、用户信息、长微博详情）共用一个「上次请求时刻」：
每次请求前只补足「目标间隔 - 已流逝时间」，解析/写盘耗掉的时间计入间隔，
不再多层延时叠加；不同类型请求也不会因为各自独立计时而连发。
"""

from __future__ import annotations

import random
import time

# 未启用防封禁时详情页的旧节奏（秒）
_LEGACY_DETAIL_DELAY = (1.0, 2.5)


def _last_request_ts(wb) -> float:
    value = getattr(wb, "_last_request_ts", 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _cfg_range(cfg: dict, low_key: str, high_key: str, default: tuple) -> tuple:
    try:
        low = float(cfg.get(low_key, default[0]))
        high = float(cfg.get(high_key, default[1]))
    except (TypeError, ValueError):
        low, high = default
    low = max(0.0, low)
    return low, max(low, high)


def detail_interval(wb) -> float:
    """长微博详情页的目标间隔。"""
    if not getattr(wb, "anti_ban_enabled", False):
        return random.uniform(*_LEGACY_DETAIL_DELAY)
    cfg = getattr(wb, "anti_ban_config", None) or {}
    return random.uniform(*_cfg_range(cfg, "detail_delay_min", "detail_delay_max", (3, 6)))


def comment_delay_range(wb) -> tuple:
    """评论请求间隔：启用防封禁时不低于 anti_ban 的评论下限。"""
    low = float(getattr(wb, "comment_request_delay_min", 1.0) or 0)
    high = float(getattr(wb, "comment_request_delay_max", 2.0) or 0)
    if getattr(wb, "anti_ban_enabled", False):
        cfg = getattr(wb, "anti_ban_config", None) or {}
        floor_low, floor_high = _cfg_range(
            cfg, "comment_delay_min", "comment_delay_max", (3, 6)
        )
        low = max(low, floor_low)
        high = max(high, floor_high)
    return low, max(low, high)


def pace(wb, interval: float, sleep_fn) -> float:
    """距上次请求不足 ``interval`` 秒时补睡差额；返回实际睡眠秒数。"""
    waited = 0.0
    last = _last_request_ts(wb)
    if interval > 0:
        remaining = interval - (time.time() - last) if last else interval
        if remaining > 0:
            sleep_fn(remaining)
            waited = remaining
    wb._last_request_ts = time.time()
    return waited
