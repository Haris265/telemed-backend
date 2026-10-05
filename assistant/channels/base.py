"""Channel protocol for outbound messages."""

from __future__ import annotations

from typing import Protocol


class Channel(Protocol):
    def send_text(self, phone: str, body: str) -> None: ...
