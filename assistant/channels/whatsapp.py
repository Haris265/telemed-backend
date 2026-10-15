"""WhatsApp Meta adapter — runs the clinic assistant engine and replies via Meta."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from django.conf import settings

from assistant.context import InboundMessage, TurnResult
from assistant.crypto import SecretDecryptionError
from assistant.engine import run_turn
from assistant.models import ClinicAssistantConfig
from assistant.phone import canonical_phone

logger = logging.getLogger(__name__)


def find_enabled_config(phone_number_id: str) -> ClinicAssistantConfig | None:
    """Return enabled clinic assistant config for this Meta phone_number_id, if any."""
    phone_number_id = (phone_number_id or "").strip()
    if not phone_number_id:
        return None
    return (
        ClinicAssistantConfig.objects.select_related("clinic", "plan")
        .filter(
            phone_number_id=phone_number_id,
            is_enabled=True,
            clinic__is_active=True,
        )
        .first()
    )


def is_whatsapp_live_ready(config: ClinicAssistantConfig) -> bool:
    """Whether this config should own inbound WhatsApp traffic for its number."""
    return config.is_whatsapp_live_ready()


def meta_client_for_config(config: ClinicAssistantConfig):
    """Build MetaWhatsAppClient from clinic token, else platform credentials."""
    from whatsapp.meta_client import MetaWhatsAppClient

    token = ""
    if config.access_token_encrypted:
        try:
            token = config.get_access_token()
        except SecretDecryptionError:
            logger.exception(
                "Failed decrypting assistant WA token for clinic_id=%s",
                config.clinic_id,
            )
            token = ""

    phone_number_id = (config.phone_number_id or "").strip()
    if token and phone_number_id:
        return MetaWhatsAppClient(token=token, phone_number_id=phone_number_id)

    # Platform fallback (same phone_number_id when testing on shared number).
    return MetaWhatsAppClient(
        token=(getattr(settings, "META_WA_TOKEN", "") or "").strip() or None,
        phone_number_id=phone_number_id
        or (getattr(settings, "META_WA_PHONE_NUMBER_ID", "") or "").strip()
        or None,
    )


def _extract_text_and_kind(msg: dict[str, Any]) -> tuple[str, Literal["text", "voice"]]:
    msg_type = (msg.get("type") or "text").strip()
    if msg_type == "text":
        return ((msg.get("text") or {}).get("body") or "").strip(), "text"
    if msg_type == "button":
        return (((msg.get("button") or {}).get("text") or "").strip()), "text"
    if msg_type == "interactive":
        interactive = msg.get("interactive") or {}
        if interactive.get("type") == "button_reply":
            return (
                ((interactive.get("button_reply") or {}).get("title") or "").strip(),
                "text",
            )
        if interactive.get("type") == "list_reply":
            return (
                ((interactive.get("list_reply") or {}).get("title") or "").strip(),
                "text",
            )
    if msg_type in ("audio", "voice"):
        # Voice STT is not wired on Meta path yet; ask patient to type.
        caption = ((msg.get("audio") or {}).get("caption") or "").strip()
        return caption, "voice"
    if msg_type == "image":
        return ((msg.get("image") or {}).get("caption") or "").strip(), "text"
    return "", "text"


def handle_meta_message(
    *,
    config: ClinicAssistantConfig,
    client,
    msg: dict[str, Any],
) -> TurnResult | None:
    """Process one Meta inbound message through the assistant engine."""
    phone_raw = str(msg.get("from") or "").strip()
    if not phone_raw:
        return None

    text, kind = _extract_text_and_kind(msg)
    if kind == "voice" and not text:
        client.send_text(
            phone_raw,
            "Voice notes are not supported on this number yet. "
            "Please type your message.",
        )
        return TurnResult(reply="", outcome="voice_unsupported", status=200)

    if not text:
        return None

    inbound = InboundMessage(
        clinic_id=int(config.clinic_id),
        phone=canonical_phone(phone_raw),
        message_id=str(msg.get("id") or uuid.uuid4().hex),
        kind=kind if kind in ("text", "voice") else "text",
        text=text,
        profile_name=str(msg.get("profile_name") or "").strip(),
    )
    result = run_turn(inbound)
    if result.reply:
        client.send_text(phone_raw, result.reply)
    return result


def handle_meta_batch(
    phone_number_id: str,
    messages: list[dict[str, Any]],
) -> bool:
    """
    If an enabled clinic assistant owns this Meta number, handle all messages
    and return True (caller should skip FSM). Otherwise return False.
    """
    config = find_enabled_config(phone_number_id)
    if config is None or not is_whatsapp_live_ready(config):
        return False

    client = meta_client_for_config(config)
    for msg in messages:
        try:
            handle_meta_message(config=config, client=client, msg=msg)
        except Exception:
            logger.exception(
                "Assistant WhatsApp failed for clinic_id=%s message_id=%s",
                config.clinic_id,
                msg.get("id"),
            )
    return True


def handle_simulate(
    *,
    clinic_id: int,
    phone: str,
    text: str,
    profile_name: str = "",
    message_id: str = "",
) -> TurnResult:
    """DEBUG helper: run assistant turn without Meta (returns TurnResult only)."""
    inbound = InboundMessage(
        clinic_id=int(clinic_id),
        phone=canonical_phone(phone),
        message_id=message_id or f"sim-asst-{uuid.uuid4().hex}",
        kind="text",
        text=text,
        profile_name=profile_name or "",
    )
    return run_turn(inbound)
