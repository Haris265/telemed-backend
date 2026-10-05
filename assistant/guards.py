"""Dedupe, rate limit, and per-patient session lock."""

from __future__ import annotations

import time
from contextlib import contextmanager

from . import settings_access as sa
from .redis_client import require_redis


class GuardRejected(Exception):
    def __init__(self, code: str, message: str, status: int = 429):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def dedupe_key(clinic_id: int, message_id: str) -> str:
    return f"{sa.KEY_PREFIX}dedupe:{clinic_id}:{message_id}"


def rate_key(clinic_id: int, phone: str) -> str:
    minute = int(time.time()) // 60
    return f"{sa.KEY_PREFIX}rl:{clinic_id}:{phone}:{minute}"


def lock_key(clinic_id: int, phone: str) -> str:
    return f"{sa.KEY_PREFIX}lock:{clinic_id}:{phone}"


def claim_dedupe(clinic_id: int, message_id: str) -> bool:
    """Return True if this message_id is new; False if duplicate."""
    if not message_id:
        return True
    return bool(
        require_redis().set(dedupe_key(clinic_id, message_id), "1", nx=True, ex=86400)
    )


def check_rate_limit(clinic_id: int, phone: str) -> None:
    client = require_redis()
    key = rate_key(clinic_id, phone)
    count = int(client.incr(key))
    if count == 1:
        client.expire(key, 120)
    if count > sa.rate_limit_per_minute():
        raise GuardRejected("rate_limited", "Please slow down.", status=429)


@contextmanager
def session_lock(clinic_id: int, phone: str, *, ttl: int = 90):
    client = require_redis()
    key = lock_key(clinic_id, phone)
    acquired = bool(client.set(key, "1", nx=True, ex=ttl))
    if not acquired:
        raise GuardRejected("session_busy", "One moment — please try again.", status=429)
    try:
        yield
    finally:
        try:
            client.delete(key)
        except Exception:
            pass


def append_trace(clinic_id: int, phone: str, entry: dict) -> None:
    if not sa.trace_enabled():
        return
    import json

    client = require_redis()
    key = f"{sa.KEY_PREFIX}trace:{clinic_id}:{phone}"
    client.rpush(key, json.dumps(entry, ensure_ascii=False))
    client.ltrim(key, -200, -1)
    client.expire(key, 86400)


def get_trace(clinic_id: int, phone: str) -> list[dict]:
    import json

    client = require_redis()
    key = f"{sa.KEY_PREFIX}trace:{clinic_id}:{phone}"
    rows = client.lrange(key, 0, -1) or []
    out = []
    for raw in rows:
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out
