"""Vendor inbound /ai-reply endpoints (raw-body HMAC). Engines unchanged."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from assistant.context import InboundMessage
from assistant.engine import run_turn
from assistant.parent_engine import ParentInboundMessage, run_parent_turn
from assistant.phone import canonical_phone
from assistant.redis_client import AssistantRedisUnavailable
from assistant.vendor.cache import get_cached_replies, set_cached_replies
from assistant.vendor.normalize import (
    bubbles_from_turn,
    normalize_incoming_messages,
    parse_clinic_id,
)
from assistant.vendor.signature import SignatureError, verify_gateway_signature

logger = logging.getLogger(__name__)

FALLBACK_REPLIES = ["One moment, we will get back to you."]
EMPTY_TEXT_REPLIES = ["Please send a text message."]
TURN_WALL_SECONDS = 22.0


def _header(request, name: str) -> str | None:
    meta_key = "HTTP_" + name.upper().replace("-", "_")
    value = request.META.get(meta_key)
    return value if value else None


def _verify(request, secrets: list[str | None]) -> None:
    verify_gateway_signature(
        secrets,
        timestamp_header=_header(request, "X-Gateway-Timestamp"),
        signature_header=_header(request, "X-Gateway-Signature"),
        raw_body=request.body,
    )


def _load_json(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    return data


def _ok_replies(replies: list[str], *, request_id: str = "") -> JsonResponse:
    if request_id:
        set_cached_replies(request_id, replies)
    return JsonResponse({"replies": replies}, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class ParentAiReplyView(View):
    """All-clinics bot: vendorContext ignored; run_parent_turn."""

    http_method_names = ["post"]

    def post(self, request):
        secrets = [
            getattr(settings, "VENDOR_PARENT_BOT_SECRET", "") or None,
            getattr(settings, "VENDOR_PARENT_BOT_SECRET_OLD", "") or None,
        ]
        try:
            _verify(request, secrets)
        except SignatureError as exc:
            logger.warning("parent ai-reply signature failed: %s", exc)
            return JsonResponse({"detail": "unauthorized"}, status=401)

        try:
            data = _load_json(request.body)
        except ValueError:
            return JsonResponse({"detail": "invalid JSON"}, status=400)

        request_id = str(data.get("requestId") or _header(request, "X-Request-Id") or "")
        cached = get_cached_replies(request_id)
        if cached is not None:
            return JsonResponse({"replies": cached}, status=200)

        phone = canonical_phone(str(data.get("senderNumber") or ""))
        if len(phone) < 10:
            return JsonResponse({"detail": "senderNumber required"}, status=400)

        normalized = normalize_incoming_messages(data.get("incomingMessages"))
        if normalized.short_circuit_replies is not None:
            return _ok_replies(normalized.short_circuit_replies, request_id=request_id)
        if not normalized.text:
            return _ok_replies(EMPTY_TEXT_REPLIES, request_id=request_id)

        name = str(data.get("senderName") or data.get("chatTitle") or "")
        started = time.monotonic()
        try:
            result = run_parent_turn(
                ParentInboundMessage(
                    phone=phone,
                    message_id=request_id or f"vendor-parent-{int(time.time())}",
                    kind=normalized.kind,
                    text=normalized.text,
                    profile_name=name,
                )
            )
        except AssistantRedisUnavailable:
            logger.exception("parent ai-reply redis down")
            return _ok_replies(FALLBACK_REPLIES, request_id=request_id)
        except Exception:
            logger.exception("parent ai-reply engine error")
            return _ok_replies(FALLBACK_REPLIES, request_id=request_id)

        if time.monotonic() - started > TURN_WALL_SECONDS and not (result.reply or "").strip():
            return _ok_replies(FALLBACK_REPLIES, request_id=request_id)

        replies = bubbles_from_turn(reply=result.reply or "", notice=result.notice)
        return _ok_replies(replies, request_id=request_id)


@method_decorator(csrf_exempt, name="dispatch")
class ClinicAiReplyView(View):
    """Clinic-locked bot: vendorContext.clinicId required; run_turn."""

    http_method_names = ["post"]

    def post(self, request):
        secrets = [
            getattr(settings, "VENDOR_CLINIC_BOT_SECRET", "") or None,
            getattr(settings, "VENDOR_CLINIC_BOT_SECRET_OLD", "") or None,
        ]
        try:
            _verify(request, secrets)
        except SignatureError as exc:
            logger.warning("clinic ai-reply signature failed: %s", exc)
            return JsonResponse({"detail": "unauthorized"}, status=401)

        try:
            data = _load_json(request.body)
        except ValueError:
            return JsonResponse({"detail": "invalid JSON"}, status=400)

        clinic_id = parse_clinic_id(data.get("vendorContext"))
        if clinic_id is None:
            return JsonResponse(
                {"detail": "vendorContext.clinicId is required"},
                status=400,
            )

        request_id = str(data.get("requestId") or _header(request, "X-Request-Id") or "")
        cached = get_cached_replies(request_id)
        if cached is not None:
            return JsonResponse({"replies": cached}, status=200)

        phone = canonical_phone(str(data.get("senderNumber") or ""))
        if len(phone) < 10:
            return JsonResponse({"detail": "senderNumber required"}, status=400)

        normalized = normalize_incoming_messages(data.get("incomingMessages"))
        if normalized.short_circuit_replies is not None:
            return _ok_replies(normalized.short_circuit_replies, request_id=request_id)
        if not normalized.text:
            return _ok_replies(EMPTY_TEXT_REPLIES, request_id=request_id)

        name = str(data.get("senderName") or data.get("chatTitle") or "")
        started = time.monotonic()
        try:
            result = run_turn(
                InboundMessage(
                    clinic_id=clinic_id,
                    phone=phone,
                    message_id=request_id or f"vendor-clinic-{int(time.time())}",
                    kind=normalized.kind,
                    text=normalized.text,
                    profile_name=name,
                )
            )
        except AssistantRedisUnavailable:
            logger.exception("clinic ai-reply redis down")
            return _ok_replies(FALLBACK_REPLIES, request_id=request_id)
        except Exception:
            logger.exception("clinic ai-reply engine error")
            return _ok_replies(FALLBACK_REPLIES, request_id=request_id)

        if time.monotonic() - started > TURN_WALL_SECONDS and not (result.reply or "").strip():
            return _ok_replies(FALLBACK_REPLIES, request_id=request_id)

        replies = bubbles_from_turn(reply=result.reply or "", notice=result.notice)
        return _ok_replies(replies, request_id=request_id)
