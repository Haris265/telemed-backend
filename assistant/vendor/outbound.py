"""Outbound send-only client: POST /v1/message-to-customer (no status poll)."""

from __future__ import annotations

import logging
from typing import Any, Literal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

Channel = Literal["parent", "clinic"]


class VendorOutboundError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _api_key(channel: Channel) -> str:
    if channel == "parent":
        return (getattr(settings, "VENDOR_PARENT_API_KEY", "") or "").strip()
    if channel == "clinic":
        return (getattr(settings, "VENDOR_CLINIC_API_KEY", "") or "").strip()
    raise VendorOutboundError(f"unknown channel: {channel}")


def _base_url() -> str:
    return (getattr(settings, "VENDOR_GATEWAY_BASE_URL", "") or "").rstrip("/")


def send_vendor_message(
    *,
    channel: Channel,
    number: str,
    message: str,
    type: str = "transactional",
    ttl_seconds: int | None = None,
    idempotency_key: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """
    Queue a WhatsApp text via the vendor gateway.

    Returns the 202 JSON body (jobId, status, ...). Does not poll status.
    """
    base = _base_url()
    key = _api_key(channel)
    if not base:
        raise VendorOutboundError("VENDOR_GATEWAY_BASE_URL is not configured")
    if not key:
        raise VendorOutboundError(f"API key for channel={channel} is not configured")

    msg = (message or "").strip()
    if not msg:
        raise VendorOutboundError("message is required")
    if len(msg) > 4000:
        raise VendorOutboundError("message exceeds 4000 characters")

    num = (number or "").strip()
    if not num:
        raise VendorOutboundError("number is required")

    msg_type = (type or "transactional").strip().lower()
    if msg_type not in ("otp", "transactional", "marketing"):
        raise VendorOutboundError("type must be otp, transactional, or marketing")

    if msg_type == "otp" and not (idempotency_key or "").strip():
        raise VendorOutboundError("Idempotency-Key is required for type=otp")

    body: dict[str, Any] = {
        "number": num,
        "message": msg,
        "type": msg_type,
    }
    if ttl_seconds is not None:
        body["ttlSeconds"] = int(ttl_seconds)

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": key,
    }
    if idempotency_key:
        headers["Idempotency-Key"] = str(idempotency_key).strip()[:256]

    url = f"{base}/v1/message-to-customer"
    try:
        response = requests.post(url, json=body, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("vendor outbound request failed channel=%s", channel)
        raise VendorOutboundError(f"vendor request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text[:500]}

    if response.status_code not in (200, 202):
        logger.warning(
            "vendor outbound error channel=%s status=%s payload=%s",
            channel,
            response.status_code,
            payload,
        )
        raise VendorOutboundError(
            f"vendor returned HTTP {response.status_code}",
            status_code=response.status_code,
            payload=payload,
        )

    job_id = payload.get("jobId") if isinstance(payload, dict) else None
    logger.info(
        "vendor outbound queued channel=%s jobId=%s status=%s",
        channel,
        job_id,
        payload.get("status") if isinstance(payload, dict) else None,
    )
    return payload if isinstance(payload, dict) else {"success": True, "raw": payload}
