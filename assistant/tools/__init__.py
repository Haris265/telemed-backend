"""Clinic-scoped LangChain tools bound to ClinicContext."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError

from assistant import settings_access as sa
from assistant.context import ClinicContext

from .appointments import build_appointment_tools
from .availability import build_availability_tools
from .booking import build_booking_tools
from .discovery import build_discovery_tools

logger = logging.getLogger(__name__)


def ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str)


def err(
    code: str,
    message: str,
    hint: str = "",
    appointment: dict | None = None,
) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message}}
    if hint:
        payload["error"]["hint"] = hint
    if appointment is not None:
        payload["error"]["appointment"] = appointment
    return json.dumps(payload, ensure_ascii=False)


def truncate_tool_result(text: str) -> str:
    max_chars = sa.tool_result_max_chars()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def wrap_tool(
    name: str,
    description: str,
    args_schema: type[BaseModel],
    fn: Callable[..., str],
) -> StructuredTool:
    def _run(**kwargs) -> str:
        try:
            validated = args_schema(**kwargs)
        except ValidationError as exc:
            return err(
                "invalid_argument",
                "Invalid tool arguments.",
                hint=str(exc.errors()[:3]),
            )
        try:
            result = fn(**validated.model_dump())
        except Exception:
            logger.exception("Tool %s failed", name)
            return err("internal_error", "Something went wrong. Please try again.")
        return truncate_tool_result(result)

    return StructuredTool.from_function(
        func=_run,
        name=name,
        description=description,
        args_schema=args_schema,
    )


def build_tools(ctx: ClinicContext, session: dict) -> list[StructuredTool]:
    tools: list[StructuredTool] = []
    tools.extend(build_discovery_tools(ctx, session))
    tools.extend(build_availability_tools(ctx, session))
    tools.extend(build_booking_tools(ctx, session))
    tools.extend(build_appointment_tools(ctx, session))
    return tools
