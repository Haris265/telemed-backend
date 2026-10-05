"""Playground HTTP adapter — returns reply in the HTTP response."""

from __future__ import annotations

from assistant.context import InboundMessage, TurnResult
from assistant.engine import run_turn
from assistant.phone import canonical_phone
from assistant.session_store import delete_session


def handle_chat(
    *,
    clinic_id: int,
    phone: str,
    message: str,
    message_id: str,
    message_type: str = "text",
    name: str = "",
) -> TurnResult:
    kind = "voice" if message_type == "voice" else "text"
    inbound = InboundMessage(
        clinic_id=int(clinic_id),
        phone=canonical_phone(phone),
        message_id=str(message_id or ""),
        kind=kind,
        text=message or "",
        profile_name=name or "",
    )
    return run_turn(inbound)


def handle_reset(*, clinic_id: int, phone: str) -> dict:
    delete_session(int(clinic_id), canonical_phone(phone))
    return {"ok": True}
