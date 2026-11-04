"""Idempotent reply cache keyed by vendor requestId."""

from __future__ import annotations

import json
import logging
from typing import Any

from assistant.redis_client import require_redis
from assistant.settings_access import KEY_PREFIX

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 15 * 60


def _key(request_id: str) -> str:
    return f"{KEY_PREFIX}vendor:req:{request_id}"


def get_cached_replies(request_id: str) -> list[str] | None:
    if not request_id:
        return None
    try:
        raw = require_redis().get(_key(request_id))
    except Exception:
        logger.exception("vendor reply cache get failed")
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    replies = data.get("replies") if isinstance(data, dict) else None
    if isinstance(replies, list) and all(isinstance(x, str) for x in replies):
        return replies
    return None


def set_cached_replies(request_id: str, replies: list[str]) -> None:
    if not request_id:
        return
    payload = json.dumps({"replies": replies}, ensure_ascii=False)
    try:
        require_redis().set(_key(request_id), payload, ex=CACHE_TTL_SECONDS)
    except Exception:
        logger.exception("vendor reply cache set failed")
