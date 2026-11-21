"""跨运行风控熔断。

一轮抓取以风控告终（HTML 风控页冷却后仍未恢复）时，把「冷却截止时刻」写到
``log/risk_state.json``；下一次启动（定时调度或 CLI）在截止前直接跳过，避免
每隔几十分钟反复撞墙、让风控升级。连续触发时冷却时长翻倍，直至上限；
一轮未触发风控即清除。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

from util.core import atomic_io
from util.core import project

FILE_NAME = "risk_state.json"
# 距上次触发超过该时长后，连续次数从 1 重新计
_STREAK_RESET_SECONDS = 24 * 3600


def state_path() -> str:
    log_dir = os.environ.get("WEIBO_LOG_DIR") or os.path.join(
        project.project_root(), "log"
    )
    return os.path.join(log_dir, FILE_NAME)


def load(path: str | None = None) -> dict:
    path = path or state_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def active_cooldown(path: str | None = None, now: float | None = None) -> dict | None:
    """冷却未结束时返回状态（含 ``remaining_seconds``），否则返回 None。"""
    state = load(path)
    now = time.time() if now is None else now
    try:
        until = float(state.get("risk_until") or 0)
    except (TypeError, ValueError):
        return None
    if until <= now:
        return None
    return {**state, "remaining_seconds": int(until - now)}


def trip(
    reason: str,
    base_minutes: float = 60,
    max_minutes: float = 360,
    path: str | None = None,
    now: float | None = None,
) -> dict:
    """记录一次风控熔断，返回新状态。"""
    path = path or state_path()
    now = time.time() if now is None else now
    prev = load(path)
    try:
        last_ts = float(prev.get("tripped_at_ts") or 0)
    except (TypeError, ValueError):
        last_ts = 0.0
    streak = int(prev.get("streak") or 0) if now - last_ts < _STREAK_RESET_SECONDS else 0
    streak += 1
    base = max(1.0, float(base_minutes or 60))
    cap = max(base, float(max_minutes or base))
    minutes = min(base * (2 ** (streak - 1)), cap)
    until = now + minutes * 60
    state = {
        "reason": str(reason or "风控"),
        "streak": streak,
        "cooldown_minutes": int(minutes),
        "tripped_at_ts": now,
        "tripped_at": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
        "risk_until": until,
        "risk_until_text": datetime.fromtimestamp(until).strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_io.atomic_write_text(path, json.dumps(state, ensure_ascii=False, indent=2))
    return state


def clear(path: str | None = None) -> bool:
    """清除熔断状态；文件不存在也返回 True。"""
    path = path or state_path()
    try:
        os.remove(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True
