"""Orchestrate one parent (multi-clinic) assistant turn for the playground."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

from catalog.models import Clinic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from . import quota
from . import settings_access as sa
from .context import TurnResult
from .eligibility import resolve_eligible_clinic
from .engine import (
    CLINIC_LIMIT_NOTICE,
    FALLBACK_REPLY,
    LLM_AUTH_REPLY,
    PATIENT_LIMIT_NOTICE,
    AssistantDisabled,
    ClinicNotFound,
    _is_llm_auth_error,
    _run_tool_loop,
    resolve_context,
)
from .guards import (
    GuardRejected,
    append_trace,
    check_rate_limit,
    claim_dedupe,
    session_lock,
)
from .llm import get_chat_model
from .parent_session import (
    PARENT_GUARD_ID,
    clear_selected_clinic,
    load_parent_session,
    save_parent_session,
)
from .phone import canonical_phone, mask_phone
from .prompts import (
    build_parent_unbound_prompt,
    build_system_prompt,
    post_process_reply,
)
from .redis_client import AssistantRedisUnavailable
from .session_store import (
    append_message,
    bump_turn,
    compact_messages,
    load_session,
    needs_compaction,
    save_session,
)
from .summarizer import summarize_messages
from .tools import build_parent_bound_tools, build_parent_unbound_tools

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParentInboundMessage:
    phone: str
    message_id: str
    kind: Literal["text", "voice"]
    text: str
    profile_name: str = ""


def _selected_clinic_meta(parent: dict) -> tuple[int | None, str]:
    cid = parent.get("selected_clinic_id")
    if not cid:
        return None, ""
    clinic = Clinic.objects.filter(pk=int(cid)).only("id", "name").first()
    if clinic is None:
        return int(cid), ""
    return clinic.id, clinic.name


def _result_with_selection(
    result: TurnResult,
    parent: dict,
) -> TurnResult:
    cid, name = _selected_clinic_meta(parent)
    result.selected_clinic_id = cid
    result.selected_clinic_name = name
    return result


def run_parent_turn(inbound: ParentInboundMessage) -> TurnResult:
    started = time.monotonic()
    phone = canonical_phone(inbound.phone)
    text = (inbound.text or "")[: sa.user_input_max_chars()]
    kind = inbound.kind if inbound.kind in ("text", "voice") else "text"
    profile_name = (inbound.profile_name or "").strip()

    try:
        if not claim_dedupe(PARENT_GUARD_ID, inbound.message_id):
            parent = load_parent_session(phone)
            return _result_with_selection(
                TurnResult(reply="", outcome="duplicate", status=200),
                parent,
            )
        check_rate_limit(PARENT_GUARD_ID, phone)
    except AssistantRedisUnavailable:
        return TurnResult(
            reply="Service temporarily unavailable.",
            outcome="redis_down",
            status=503,
        )
    except GuardRejected as exc:
        return TurnResult(reply=exc.message, outcome=exc.code, status=exc.status)

    try:
        with session_lock(PARENT_GUARD_ID, phone):
            parent = load_parent_session(phone)
            if profile_name and not parent.get("patient_name"):
                parent["patient_name"] = profile_name

            selected_id = parent.get("selected_clinic_id")
            if selected_id:
                # Drop selection if clinic became ineligible.
                if resolve_eligible_clinic(int(selected_id)) is None:
                    clear_selected_clinic(parent)
                    selected_id = None

            if not selected_id:
                return _run_unbound(
                    parent=parent,
                    phone=phone,
                    text=text,
                    kind=kind,
                    started=started,
                )

            return _run_bound(
                parent=parent,
                phone=phone,
                text=text,
                kind=kind,
                started=started,
                clinic_id=int(selected_id),
            )
    except GuardRejected as exc:
        return TurnResult(reply=exc.message, outcome=exc.code, status=exc.status)
    except AssistantRedisUnavailable:
        return TurnResult(
            reply="Service temporarily unavailable.",
            outcome="redis_down",
            status=503,
        )


def _run_unbound(
    *,
    parent: dict,
    phone: str,
    text: str,
    kind: str,
    started: float,
) -> TurnResult:
    turn_no = bump_turn(parent)
    tools = build_parent_unbound_tools(parent)
    system = build_parent_unbound_prompt(parent, latest_user_text=text)
    messages: list = [SystemMessage(content=system)]
    for msg in parent.get("messages") or []:
        if msg.get("r") == "user":
            messages.append(HumanMessage(content=msg.get("c") or ""))
        else:
            messages.append(AIMessage(content=msg.get("c") or ""))
    messages.append(HumanMessage(content=text))

    deadline = started + sa.turn_time_budget_seconds()
    try:
        model = get_chat_model()
        ai = _run_tool_loop(model, tools, messages, deadline=deadline)
        reply = post_process_reply(getattr(ai, "content", None) or FALLBACK_REPLY)
        if not reply:
            reply = FALLBACK_REPLY
        append_message(parent, "user", text)
        append_message(parent, "assistant", reply)
        if needs_compaction(parent):
            keep = sa.keep_after_compact()
            older = (parent.get("messages") or [])[:-keep]
            summary = summarize_messages(parent.get("summary") or "", older)
            compact_messages(parent, summary)
        save_parent_session(parent)
        append_trace(
            PARENT_GUARD_ID,
            phone,
            {
                "turn": turn_no,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "outcome": "ok",
                "mode": "parent_unbound",
                "masked_phone": mask_phone(phone),
            },
        )
        return _result_with_selection(
            TurnResult(
                reply=reply,
                session_id=parent.get("session_id") or "",
                quota={},
                outcome="ok",
                status=200,
            ),
            parent,
        )
    except Exception as exc:
        logger.exception(
            "parent_turn unbound failed phone=%s",
            mask_phone(phone),
        )
        save_parent_session(parent)
        if _is_llm_auth_error(exc):
            return _result_with_selection(
                TurnResult(
                    reply=LLM_AUTH_REPLY,
                    session_id=parent.get("session_id") or "",
                    outcome="llm_auth_error",
                    status=503,
                ),
                parent,
            )
        return _result_with_selection(
            TurnResult(
                reply=FALLBACK_REPLY,
                session_id=parent.get("session_id") or "",
                outcome="llm_error",
                status=503,
            ),
            parent,
        )


def _run_bound(
    *,
    parent: dict,
    phone: str,
    text: str,
    kind: str,
    started: float,
    clinic_id: int,
) -> TurnResult:
    from .context import InboundMessage

    try:
        ctx = resolve_context(
            InboundMessage(
                clinic_id=clinic_id,
                phone=phone,
                message_id="",
                kind="text",
                text=text,
                profile_name=parent.get("patient_name") or "",
            )
        )
    except ClinicNotFound:
        clear_selected_clinic(parent)
        save_parent_session(parent)
        return _result_with_selection(
            TurnResult(reply="Clinic not found.", outcome="not_found", status=404),
            parent,
        )
    except AssistantDisabled:
        clear_selected_clinic(parent)
        save_parent_session(parent)
        return _result_with_selection(
            TurnResult(
                reply="This clinic assistant is not enabled.",
                outcome="disabled",
                status=403,
            ),
            parent,
        )

    if quota.patient_at_cap(ctx.clinic_id, ctx.phone, ctx.plan):
        notice = None
        reply = ""
        if quota.claim_patient_notice(ctx.clinic_id, ctx.phone):
            notice = "patient_limit"
            reply = PATIENT_LIMIT_NOTICE
        save_parent_session(parent)
        return _result_with_selection(
            TurnResult(
                reply=reply,
                notice=notice,
                outcome="patient_limit",
                status=200,
                quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
            ),
            parent,
        )

    if not quota.reserve_day_slot(ctx.clinic_id, kind, ctx.plan):
        notice = None
        reply = ""
        if quota.claim_day_notice(ctx.clinic_id, kind):
            notice = "clinic_limit"
            reply = CLINIC_LIMIT_NOTICE
        save_parent_session(parent)
        return _result_with_selection(
            TurnResult(
                reply=reply,
                notice=notice,
                outcome="clinic_limit",
                status=200,
                quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
            ),
            parent,
        )

    clinic_session = load_session(ctx.clinic_id, ctx.phone)
    if parent.get("patient_name") and not clinic_session.get("patient_name"):
        clinic_session["patient_name"] = parent["patient_name"]
    if ctx.patient_name and not clinic_session.get("patient_name"):
        clinic_session["patient_name"] = ctx.patient_name

    turn_no = bump_turn(parent)
    tools = build_parent_bound_tools(ctx, clinic_session, parent)
    system = build_system_prompt(
        ctx,
        clinic_session,
        latest_user_text=text,
        parent_bound=True,
    )
    messages: list = [SystemMessage(content=system)]
    for msg in parent.get("messages") or []:
        if msg.get("r") == "user":
            messages.append(HumanMessage(content=msg.get("c") or ""))
        else:
            messages.append(AIMessage(content=msg.get("c") or ""))
    messages.append(HumanMessage(content=text))

    deadline = started + sa.turn_time_budget_seconds()
    try:
        model = get_chat_model()
        ai = _run_tool_loop(model, tools, messages, deadline=deadline)
        reply = post_process_reply(getattr(ai, "content", None) or FALLBACK_REPLY)
        if not reply:
            reply = FALLBACK_REPLY
        quota.count_patient_reply(ctx.clinic_id, ctx.phone)
        append_message(parent, "user", text)
        append_message(parent, "assistant", reply)
        if needs_compaction(parent):
            keep = sa.keep_after_compact()
            older = (parent.get("messages") or [])[:-keep]
            summary = summarize_messages(parent.get("summary") or "", older)
            compact_messages(parent, summary)
        save_session(clinic_session)
        save_parent_session(parent)
        snap = quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict()
        append_trace(
            ctx.clinic_id,
            ctx.phone,
            {
                "turn": turn_no,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "outcome": "ok",
                "mode": "parent_bound",
                "masked_phone": mask_phone(ctx.phone),
            },
        )
        return _result_with_selection(
            TurnResult(
                reply=reply,
                session_id=parent.get("session_id") or "",
                quota=snap,
                outcome="ok",
                status=200,
            ),
            parent,
        )
    except Exception as exc:
        logger.exception(
            "parent_turn bound failed clinic_id=%s phone=%s",
            ctx.clinic_id,
            mask_phone(ctx.phone),
        )
        quota.refund_day_slot(ctx.clinic_id, kind)
        save_parent_session(parent)
        if _is_llm_auth_error(exc):
            return _result_with_selection(
                TurnResult(
                    reply=LLM_AUTH_REPLY,
                    session_id=parent.get("session_id") or "",
                    quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
                    outcome="llm_auth_error",
                    status=503,
                ),
                parent,
            )
        return _result_with_selection(
            TurnResult(
                reply=FALLBACK_REPLY,
                session_id=parent.get("session_id") or "",
                quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
                outcome="llm_error",
                status=503,
            ),
            parent,
        )
