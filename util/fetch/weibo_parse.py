"""单条微博解析。"""

from __future__ import annotations

import logging

from util.core import archive_state

logger = logging.getLogger("weibo")


_UNSAFE_SKIP_MODES = ("mysql", "mongo", "mongodb", "post")


def can_skip_long_text(wb, weibo_id, weibo_info) -> bool:
    """已完整存档且未再编辑的长微博可跳过详情页请求（列表页截断正文不会覆盖存档）。

    条件：markdown 存档 + 状态索引记录过完整全文与编辑次数，且编辑次数未变。
    mysql/mongo/post 后端会用截断正文覆盖，此时不跳过。
    """
    write_mode = getattr(wb, "write_mode", None) or []
    if "markdown" not in write_mode or any(m in write_mode for m in _UNSAFE_SKIP_MODES):
        return False
    ensure_state = getattr(wb, "_ensure_archive_state", None)
    if not callable(ensure_state):
        return False
    try:
        item = archive_state.get_weibo(ensure_state(), weibo_id)
    except Exception:  # noqa: BLE001 状态索引不可用时按需请求详情
        return False
    if not item or not item.get("content_hash") or not item.get("md_path"):
        return False
    if item.get("status", archive_state.STATUS_ACTIVE) != archive_state.STATUS_ACTIVE:
        return False
    if "edit_count" not in item or item.get("long_text_incomplete"):
        return False
    try:
        return int(item["edit_count"]) == int(weibo_info.get("edit_count") or 0)
    except (TypeError, ValueError):
        return False


def get_one_weibo(wb, info) -> object:
    """获取一条微博的全部信息"""
    try:
        weibo_info = info["mblog"]
        weibo_id = weibo_info["id"]
        retweeted_status = weibo_info.get("retweeted_status")
        is_long = (
            True if weibo_info.get("pic_num") > 9 else weibo_info.get("isLongText")
        )
        is_long_retweet = bool(
            retweeted_status and retweeted_status.get("isLongText")
        )
        long_skipped = (is_long or is_long_retweet) and can_skip_long_text(
            wb, weibo_id, weibo_info
        )
        if long_skipped:
            logger.debug("长微博已完整存档且未编辑，跳过详情页: %s", weibo_id)
            is_long = False
            is_long_retweet = False
        if retweeted_status and retweeted_status.get("id"):  # 转发
            retweet_id = retweeted_status.get("id")
            if is_long:
                weibo = wb.get_long_weibo(weibo_id)
                if not weibo:
                    weibo = wb.parse_weibo(weibo_info)
                    weibo["long_text_failed"] = True
            else:
                weibo = wb.parse_weibo(weibo_info)
            if is_long_retweet:
                retweet = wb.get_long_weibo(retweet_id)
                if not retweet:
                    retweet = wb.parse_weibo(retweeted_status)
                    retweet["long_text_failed"] = True
            else:
                retweet = wb.parse_weibo(retweeted_status)
            (
                retweet["created_at"],
                retweet["full_created_at"],
            ) = wb.standardize_date(retweeted_status["created_at"])
            weibo["retweet"] = retweet
        else:  # 原创
            if is_long:
                weibo = wb.get_long_weibo(weibo_id)
                if not weibo:
                    weibo = wb.parse_weibo(weibo_info)
                    weibo["long_text_failed"] = True
            else:
                weibo = wb.parse_weibo(weibo_info)
        if long_skipped:
            weibo["long_text_skipped"] = True
        weibo["created_at"], weibo["full_created_at"] = wb.standardize_date(
            weibo_info["created_at"]
        )
        edit_count = weibo_info.get("edit_count", 0)
        weibo["edited"] = edit_count > 0
        weibo["edit_count"] = edit_count
        # 可见性与最后编辑时间（编辑检测与变化报告用）
        weibo["edit_at"] = str(weibo_info.get("edit_at") or "")
        weibo["visible"] = archive_state.normalize_visibility(
            weibo_info.get("visible")
        )
        return weibo
    except Exception as e:  # noqa: BLE001 兜底：单点失败不阻断主流程
        # 单条微博解析失败不静默：计数并在本轮结束时告警，
        # 便于发现接口字段变化导致的大面积漏抓。
        wb.crawl_success = getattr(wb, "crawl_success", None) or {}
        wb.crawl_success["parse_failures"] = (
            int(wb.crawl_success.get("parse_failures", 0)) + 1
        )
        logger.exception("解析微博失败（已跳过该条）: %s", e)
