"""Dedicated fail-closed Redis client for assistant sessions and quotas."""

from __future__ import annotations

import logging
from functools import lru_cache

import redis
from django.core.exceptions import ImproperlyConfigured

from . import settings_access as sa

logger = logging.getLogger(__name__)


class AssistantRedisUnavailable(Exception):
    """Raised when the assistant Redis backend cannot be reached."""


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    url = sa.redis_url()
    if not url:
        raise ImproperlyConfigured("ASSISTANT_REDIS_URL is not configured")
    return redis.Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
        health_check_interval=30,
    )


def reset_redis_client() -> None:
    """Clear the cached client (used by tests)."""
    get_redis.cache_clear()


def ping_redis() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception as exc:
        logger.warning("Assistant Redis ping failed: %s", exc)
        return False


def require_redis() -> redis.Redis:
    try:
        client = get_redis()
        if not client.ping():
            raise AssistantRedisUnavailable("Redis ping returned false")
        return client
    except AssistantRedisUnavailable:
        raise
    except Exception as exc:
        raise AssistantRedisUnavailable(str(exc)) from exc
