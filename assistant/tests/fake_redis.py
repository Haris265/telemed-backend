"""Minimal in-memory Redis stand-in (fakeredis substitute when package unavailable)."""

from __future__ import annotations

import time
from typing import Any


class FakeRedis:
    def __init__(self):
        self._kv: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}
        self._lists: dict[str, list[str]] = {}

    def _purge(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and time.time() >= exp:
            self._kv.pop(key, None)
            self._lists.pop(key, None)
            self._expiry.pop(key, None)

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        self._purge(key)
        return self._kv.get(key)

    def set(self, key: str, value, nx: bool = False, ex: int | None = None):
        self._purge(key)
        if nx and key in self._kv:
            return False
        self._kv[key] = str(value)
        if ex is not None:
            self._expiry[key] = time.time() + int(ex)
        return True

    def delete(self, *keys):
        n = 0
        for key in keys:
            if key in self._kv or key in self._lists:
                self._kv.pop(key, None)
                self._lists.pop(key, None)
                self._expiry.pop(key, None)
                n += 1
        return n

    def incr(self, key: str) -> int:
        self._purge(key)
        value = int(self._kv.get(key) or 0) + 1
        self._kv[key] = str(value)
        return value

    def decr(self, key: str) -> int:
        self._purge(key)
        value = int(self._kv.get(key) or 0) - 1
        self._kv[key] = str(value)
        return value

    def expire(self, key: str, seconds: int) -> bool:
        self._purge(key)
        if key not in self._kv and key not in self._lists:
            return False
        self._expiry[key] = time.time() + int(seconds)
        return True

    def rpush(self, key: str, *values):
        self._purge(key)
        self._lists.setdefault(key, []).extend(str(v) for v in values)
        return len(self._lists[key])

    def ltrim(self, key: str, start: int, end: int):
        self._purge(key)
        lst = self._lists.get(key) or []
        if end == -1:
            end = len(lst) - 1
        # redis ltrim with negative start like -200
        if start < 0:
            start = max(0, len(lst) + start)
        self._lists[key] = lst[start : end + 1]
        return True

    def lrange(self, key: str, start: int, end: int):
        self._purge(key)
        lst = self._lists.get(key) or []
        if end == -1:
            end = len(lst) - 1
        if start < 0:
            start = max(0, len(lst) + start)
        return lst[start : end + 1]

    def eval(self, script: str, numkeys: int, *keys_and_args):
        keys = list(keys_and_args[:numkeys])
        args = list(keys_and_args[numkeys:])
        # Reserve script
        if "INCR" in script and "DECR" in script and "EXPIRE" in script:
            key = keys[0]
            cap = int(args[0])
            ttl = int(args[1]) if len(args) > 1 else 0
            current = self.incr(key)
            if ttl > 0:
                self.expire(key, ttl)
            if current > cap:
                self.decr(key)
                return 0
            return 1
        # Refund script
        if "DECR" in script:
            key = keys[0]
            current = int(self.get(key) or 0)
            if current > 0:
                return self.decr(key)
            return 0
        raise NotImplementedError("Unsupported Lua script in FakeRedis")
