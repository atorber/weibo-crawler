"""Weibo Direct Message & Group Chat (pcweibochat / api.weibo.com/webim) client."""

from util.chat.weibo_chat import (
    DEFAULT_CHUNK_KB,
    MAX_CHAT_IMAGE_BYTES,
    WEBIM_BASE_URL,
    WEBIM_REFERER,
    WEBIM_SOURCE,
    WeiboChatClient,
    is_group_id,
)

__all__ = [
    "DEFAULT_CHUNK_KB",
    "MAX_CHAT_IMAGE_BYTES",
    "WEBIM_BASE_URL",
    "WEBIM_REFERER",
    "WEBIM_SOURCE",
    "WeiboChatClient",
    "is_group_id",
]
