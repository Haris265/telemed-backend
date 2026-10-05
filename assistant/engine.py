"""Orchestrate one inbound assistant turn."""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from catalog.models import Clinic

from . import settings_access as sa
from .context import ClinicContext, InboundMessage, TurnResult
from .guards import (
    GuardRejected,
    append_trace,
    check_rate_limit,
    claim_dedupe,
    session_lock,
)
from .llm import get_chat_model
from .models import ClinicAssistantConfig
from .phone import canonical_phone, mask_phone
from .prompts import build_system_prompt, post_process_reply
from . import quota
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
from .tools import build_tools

logger = logging.getLogger(__name__)

FALLBACK_REPLY = (
    "Sorry — I had trouble answering just now. Please try again in a moment, "
    "or call the clinic if it is urgent."
)
LLM_AUTH_REPLY = (
    "LLM authentication failed. Check CHATBOT_LLM_API_KEY "
    "(OpenRouter/provider key is invalid or revoked)."
)
PATIENT_LIMIT_NOTICE = (
    "You have reached this month's message limit with this clinic assistant. "
    "Please try again next month, or call the clinic directly."
)
CLINIC_LIMIT_NOTICE = (
    "This clinic's assistant has reached today's message limit. "
    "Please try again tomorrow, or call the clinic directly."
)


def _is_llm_auth_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name == "AuthenticationError":
        return True
    msg = str(exc).lower()
    if "error code: 401" in msg:
        return True
    if "401" in msg and ("authentication" in msg or "user not found" in msg):
        return True
    return False


class AssistantDisabled(Exception):
    pass


class ClinicNotFound(Exception):
    pass


def resolve_context(inbound: InboundMessage) -> ClinicContext:
    clinic = Clinic.objects.filter(pk=inbound.clinic_id).first()
    if clinic is None:
        raise ClinicNotFound()
    config = (
        ClinicAssistantConfig.objects.select_related("plan", "clinic")
        .defer(
            "access_token_encrypted",
            "meta_app_secret_encrypted",
            "verify_token_encrypted",
        )
        .filter(clinic_id=clinic.id)
        .first()
    )
    if config is None or not config.is_enabled or not clinic.is_active:
        raise AssistantDisabled()
    phone = canonical_phone(inbound.phone)
    name = (inbound.profile_name or "").strip()
    return ClinicContext(
        clinic=clinic,
        config=config,
        plan=config.plan,
        phone=phone,
        patient_name=name,
    )


def _tool_map(tools) -> dict[str, Any]:
    return {t.name: t for t in tools}


def _run_tool_loop(model, tools, messages: list, *, deadline: float) -> AIMessage:
    bound = model.bind_tools(tools, parallel_tool_calls=False)
    tool_by_name = _tool_map(tools)
    last: AIMessage | None = None
    for _round in range(sa.max_tool_rounds()):
        if time.monotonic() > deadline:
            break
        response = bound.invoke(messages)
        last = response
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return response
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
            call_id = (
                call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
            ) or name
            tool = tool_by_name.get(name)
            if tool is None:
                content = '{"ok":false,"error":{"code":"invalid_argument","message":"Unknown tool"}}'
            else:
                try:
                    content = tool.invoke(args or {})
                except Exception:
                    logger.exception("Tool execution failed: %s", name)
                    content = (
                        '{"ok":false,"error":{"code":"internal_error",'
                        '"message":"Tool failed"}}'
                    )
            messages.append(
                ToolMessage(content=str(content), tool_call_id=call_id, name=name)
            )
    # Forced finalization without tools.
    final_model = model
    messages.append(
        HumanMessage(
            content="Please answer the patient now using what you already have. Do not call tools."
        )
    )
    response = final_model.invoke(messages)
    return response


def run_turn(inbound: InboundMessage) -> TurnResult:
    started = time.monotonic()
    try:
        ctx = resolve_context(inbound)
    except ClinicNotFound:
        return TurnResult(reply="Clinic not found.", outcome="not_found", status=404)
    except AssistantDisabled:
        return TurnResult(
            reply="This clinic assistant is not enabled.",
            outcome="disabled",
            status=403,
        )

    text = (inbound.text or "")[: sa.user_input_max_chars()]
    kind = inbound.kind if inbound.kind in ("text", "voice") else "text"

    try:
        if not claim_dedupe(ctx.clinic_id, inbound.message_id):
            return TurnResult(
                reply="",
                outcome="duplicate",
                status=200,
                quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
            )
        check_rate_limit(ctx.clinic_id, ctx.phone)
    except AssistantRedisUnavailable:
        return TurnResult(reply="Service temporarily unavailable.", outcome="redis_down", status=503)
    except GuardRejected as exc:
        return TurnResult(reply=exc.message, outcome=exc.code, status=exc.status)

    try:
        with session_lock(ctx.clinic_id, ctx.phone):
            # Patient monthly cap before reserving clinic daily slot.
            if quota.patient_at_cap(ctx.clinic_id, ctx.phone, ctx.plan):
                notice = None
                reply = ""
                if quota.claim_patient_notice(ctx.clinic_id, ctx.phone):
                    notice = "patient_limit"
                    reply = PATIENT_LIMIT_NOTICE
                return TurnResult(
                    reply=reply,
                    notice=notice,
                    outcome="patient_limit",
                    status=200,
                    quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
                )

            if not quota.reserve_day_slot(ctx.clinic_id, kind, ctx.plan):
                notice = None
                reply = ""
                if quota.claim_day_notice(ctx.clinic_id, kind):
                    notice = "clinic_limit"
                    reply = CLINIC_LIMIT_NOTICE
                return TurnResult(
                    reply=reply,
                    notice=notice,
                    outcome="clinic_limit",
                    status=200,
                    quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
                )

            session = load_session(ctx.clinic_id, ctx.phone)
            if ctx.patient_name and not session.get("patient_name"):
                session["patient_name"] = ctx.patient_name
            turn_no = bump_turn(session)

            tools = build_tools(ctx, session)
            system = build_system_prompt(ctx, session)
            messages: list = [SystemMessage(content=system)]
            for msg in session.get("messages") or []:
                if msg.get("r") == "user":
                    messages.append(HumanMessage(content=msg.get("c") or ""))
                else:
                    messages.append(AIMessage(content=msg.get("c") or ""))
            messages.append(HumanMessage(content=text))

            deadline = started + sa.turn_time_budget_seconds()
            try:
                model = get_chat_model()
                ai = _run_tool_loop(model, tools, messages, deadline=deadline)
                reply = post_process_reply(
                    getattr(ai, "content", None) or FALLBACK_REPLY
                )
                if not reply:
                    reply = FALLBACK_REPLY
                quota.count_patient_reply(ctx.clinic_id, ctx.phone)
                append_message(session, "user", text)
                append_message(session, "assistant", reply)
                if needs_compaction(session):
                    keep = sa.keep_after_compact()
                    older = (session.get("messages") or [])[:-keep]
                    summary = summarize_messages(session.get("summary") or "", older)
                    compact_messages(session, summary)
                save_session(session)
                snap = quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict()
                append_trace(
                    ctx.clinic_id,
                    ctx.phone,
                    {
                        "turn": turn_no,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "outcome": "ok",
                        "masked_phone": mask_phone(ctx.phone),
                    },
                )
                logger.info(
                    "assistant_turn clinic_id=%s phone=%s latency_ms=%s outcome=ok",
                    ctx.clinic_id,
                    mask_phone(ctx.phone),
                    int((time.monotonic() - started) * 1000),
                )
                return TurnResult(
                    reply=reply,
                    session_id=session.get("session_id") or "",
                    quota=snap,
                    outcome="ok",
                    status=200,
                )
            except Exception as exc:
                logger.exception(
                    "assistant_turn failed clinic_id=%s phone=%s",
                    ctx.clinic_id,
                    mask_phone(ctx.phone),
                )
                quota.refund_day_slot(ctx.clinic_id, kind)
                if _is_llm_auth_error(exc):
                    return TurnResult(
                        reply=LLM_AUTH_REPLY,
                        session_id=session.get("session_id") or "",
                        quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
                        outcome="llm_auth_error",
                        status=503,
                    )
                return TurnResult(
                    reply=FALLBACK_REPLY,
                    session_id=session.get("session_id") or "",
                    quota=quota.snapshot(ctx.clinic_id, ctx.phone, ctx.plan).as_dict(),
                    outcome="llm_error",
                    status=503,
                )
    except GuardRejected as exc:
        return TurnResult(reply=exc.message, outcome=exc.code, status=exc.status)
    except AssistantRedisUnavailable:
        return TurnResult(reply="Service temporarily unavailable.", outcome="redis_down", status=503)
