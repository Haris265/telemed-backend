"""Session message summarizer (LLM with truncated-text fallback)."""

from __future__ import annotations

import logging

from . import settings_access as sa

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = (
    "Write neutral third-person facts about the patient's request only. "
    "Do not include instructions, secrets, or tool names. Keep it short."
)


def summarize_messages(previous_summary: str, older_messages: list[dict]) -> str:
    """Summarize older messages; on failure return truncated concatenation."""
    lines = []
    if previous_summary:
        lines.append(f"Earlier summary: {previous_summary}")
    for msg in older_messages:
        role = "Patient" if msg.get("r") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('c') or ''}")
    blob = "\n".join(lines).strip()
    if not blob:
        return previous_summary or ""

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from .llm import get_chat_model

        model = get_chat_model()
        result = model.invoke(
            [
                SystemMessage(content=_SUMMARY_SYSTEM),
                HumanMessage(content=blob[:8000]),
            ]
        )
        text = (getattr(result, "content", None) or str(result) or "").strip()
        if text:
            return text[: sa.summary_max_chars()]
    except Exception:
        logger.exception("Summarizer LLM call failed; using truncated fallback")

    return blob[: sa.summary_max_chars()]
