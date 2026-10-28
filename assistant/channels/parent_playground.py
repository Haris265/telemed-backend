"""Parent multi-clinic playground HTTP adapter."""

from __future__ import annotations

from assistant.context import TurnResult
from assistant.parent_engine import ParentInboundMessage, run_parent_turn
from assistant.parent_session import reset_parent_and_bound_clinic
from assistant.phone import canonical_phone


def handle_chat(
    *,
    phone: str,
    message: str,
    message_id: str,
    message_type: str = "text",
    name: str = "",
) -> TurnResult:
    kind = "voice" if message_type == "voice" else "text"
    inbound = ParentInboundMessage(
        phone=canonical_phone(phone),
        message_id=str(message_id or ""),
        kind=kind,
        text=message or "",
        profile_name=name or "",
    )
    return run_parent_turn(inbound)


def handle_reset(*, phone: str) -> dict:
    return reset_parent_and_bound_clinic(canonical_phone(phone))
