"""Shared test helpers: patch Redis client with FakeRedis."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from assistant.redis_client import reset_redis_client
from assistant.tests.fake_redis import FakeRedis


@contextmanager
def fake_redis_client():
    client = FakeRedis()
    reset_redis_client()
    with patch("assistant.redis_client.get_redis", return_value=client):
        with patch("assistant.redis_client.require_redis", return_value=client):
            yield client
    reset_redis_client()
