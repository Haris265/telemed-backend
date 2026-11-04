"""Normalize vendor contract incomingMessages into one engine text turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class NormalizedInbound:
    text: str
    kind: Literal["text", "voice"]
    short_circuit_replies: list[str] | None = None


_LARGE_FILE_REPLY = (
    "File bohat bari hai. Chhoti file ya text bhejein."
)
_VOICE_FAIL_REPLY = (
    "Voice note samajh nahi aayi. Please apna message type kar dein."
)
_MEDIA_TEXT_ONLY_REPLY = (
    "Appointment ke liye text likhein. Image/PDF se booking abhi support nahi."
)


def _item_text(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "").strip()
    media = item.get("media")
    if isinstance(media, dict):
        caption = str(media.get("caption") or "").strip()
        if caption and caption not in text:
            text = f"{text}\n{caption}".strip() if text else caption
    return text


def normalize_incoming_messages(incoming: Any) -> NormalizedInbound:
    """
    Combine vendor incomingMessages into one text for run_turn / run_parent_turn.

    Does not call the AI engine. Large-file / unsupported-media short-circuits
    return polite replies without an engine call.
    """
    if not isinstance(incoming, list) or not incoming:
        return NormalizedInbound(text="", kind="text", short_circuit_replies=None)

    parts: list[str] = []
    saw_voice = False
    saw_unsupported_media_only = False
    large_file = False

    for raw in incoming:
        if not isinstance(raw, dict):
            continue
        media = raw.get("media")
        text = _item_text(raw)

        if media is None:
            if text:
                parts.append(text)
            continue

        if not isinstance(media, dict):
            if text:
                parts.append(text)
            continue

        if media.get("skippedLargeFile") or media.get("skippedCombinedLimit"):
            large_file = True
            continue
        if media.get("base64Data") is None and media.get("hasMedia"):
            large_file = True
            continue

        media_type = str(media.get("mediaType") or "").lower()
        if media_type in ("ptt", "audio"):
            saw_voice = True
            # STT not wired in Phase 1 — caption/text only; else short-circuit later.
            if text:
                parts.append(text)
            continue
        if media_type == "sticker":
            continue
        if media_type in ("image", "document"):
            if text:
                parts.append(text)
            else:
                saw_unsupported_media_only = True
            continue
        if text:
            parts.append(text)

    if large_file and not parts:
        return NormalizedInbound(
            text="", kind="text", short_circuit_replies=[_LARGE_FILE_REPLY]
        )

    combined = "\n".join(parts).strip()
    if combined:
        # Caption/text from voice notes still goes to the engine as text.
        return NormalizedInbound(text=combined, kind="text", short_circuit_replies=None)

    if saw_voice:
        return NormalizedInbound(
            text="", kind="voice", short_circuit_replies=[_VOICE_FAIL_REPLY]
        )
    if large_file:
        return NormalizedInbound(
            text="", kind="text", short_circuit_replies=[_LARGE_FILE_REPLY]
        )
    if saw_unsupported_media_only:
        return NormalizedInbound(
            text="", kind="text", short_circuit_replies=[_MEDIA_TEXT_ONLY_REPLY]
        )
    return NormalizedInbound(text="", kind="text", short_circuit_replies=None)


def parse_clinic_id(vendor_context: Any) -> int | None:
    if not isinstance(vendor_context, dict):
        return None
    raw = vendor_context.get("clinicId")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def bubbles_from_turn(*, reply: str, notice: str | None = None) -> list[str]:
    """Map TurnResult fields to contract replies (max 5 bubbles, 4000 chars)."""
    out: list[str] = []
    if notice and str(notice).strip():
        out.append(str(notice).strip()[:4000])
    if reply and str(reply).strip():
        out.append(str(reply).strip()[:4000])
    return out[:5]
