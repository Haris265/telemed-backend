"""HMAC signature verification for vendor gateway inbound requests."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Iterable


class SignatureError(Exception):
    """Request failed gateway signature / timestamp checks."""


def _parse_signatures(header: str) -> list[str]:
    parts: list[str] = []
    for chunk in (header or "").split(","):
        token = chunk.strip()
        if token.startswith("v1="):
            token = token[3:]
        if token:
            parts.append(token)
    return parts


def compute_signature(secret: str, timestamp: int | str, raw_body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()


def verify_gateway_signature(
    secrets: Iterable[str | None],
    *,
    timestamp_header: str | None,
    signature_header: str | None,
    raw_body: bytes,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> None:
    """
    Verify X-Gateway-Timestamp + X-Gateway-Signature against one or more secrets.

    Accepts comma-separated ``v1=...`` values (secret rotation). Raises SignatureError on failure.
    """
    active = [s for s in secrets if s]
    if not active:
        raise SignatureError("bot secret not configured")

    if not timestamp_header or not signature_header:
        raise SignatureError("missing signature headers")

    try:
        ts = int(timestamp_header)
    except (TypeError, ValueError) as exc:
        raise SignatureError("invalid timestamp") from exc

    current = time.time() if now is None else now
    if abs(current - ts) > tolerance_seconds:
        raise SignatureError("stale request")

    given = _parse_signatures(signature_header)
    if not given:
        raise SignatureError("empty signature")

    for secret in active:
        expected = compute_signature(secret, ts, raw_body)
        if any(
            hmac.compare_digest(expected, g)
            for g in given
            if len(g) == len(expected)
        ):
            return

    raise SignatureError("bad signature")
