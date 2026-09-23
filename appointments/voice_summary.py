"""Generate Roman Urdu visit summaries from voice attachments via Google Gemini."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PK_TZ = ZoneInfo("Asia/Karachi")

PROMPT = """You are a medical scribe for a Pakistani telemedicine clinic.
Listen to this doctor visit voice note.

Return ONLY valid JSON (no markdown fences) with exactly these keys:
{
  "transcript": "full speech-to-text of the audio (Urdu/English as spoken)",
  "summary": "concise clinical visit summary in Roman Urdu (Urdu written only in Latin/English letters — no Arabic or Devanagari script)",
  "next_visit_at": "YYYY-MM-DDTHH:MM or null"
}

Summary rules:
- Include patient complaints, findings, advice, medicines if mentioned.
- Keep summary short (4-8 lines).
- Do not invent details that are not in the audio.
- If audio is empty or unusable, set transcript to "" and summary to:
  "Voice note se clear summary nahi ban saki."
- If the doctor mentions a next / follow-up visit date (and optional time), set next_visit_at
  as local Pakistan time in format YYYY-MM-DDTHH:MM (use 10:00 if only a date is given).
- If no next visit is mentioned, set next_visit_at to null.
"""

FOLLOW_UP_EXTRACT_PROMPT = """From this Roman Urdu clinical visit summary, extract the next/follow-up visit datetime.
Return ONLY JSON: {"next_visit_at": "YYYY-MM-DDTHH:MM" or null}
Use Asia/Karachi local time. If only a date is mentioned, use 10:00.
If no follow-up visit is mentioned, return null.
Summary:
"""

MIME_BY_EXT = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".3gp": "audio/3gpp",
}

# Prefer capacity-friendly models; env primary is tried first.
FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.6-flash")
RETRYABLE_STATUS = {429, 503}
RETRY_BACKOFF_SECONDS = (1, 2, 4)


def _gemini_key() -> str:
    return (
        getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    ).strip()


def _summary_model() -> str:
    return (
        getattr(settings, "GEMINI_SUMMARY_MODEL", "")
        or os.getenv("GEMINI_SUMMARY_MODEL", "gemini-3.5-flash-lite")
        or "gemini-3.5-flash-lite"
    ).strip()


def _model_chain() -> list[str]:
    primary = _summary_model()
    chain: list[str] = []
    for name in (primary, *FALLBACK_MODELS):
        if name and name not in chain:
            chain.append(name)
    return chain


def _audio_mime(path: str, declared: str) -> str:
    mime = (declared or "").strip().lower()
    if mime and mime not in ("application/octet-stream", "audio/m4a", "audio/x-m4a"):
        return mime
    if mime in ("audio/m4a", "audio/x-m4a"):
        return "audio/mp4"
    ext = Path(path).suffix.lower()
    return MIME_BY_EXT.get(ext, "audio/mp4")


def _fail(attachment, message: str) -> None:
    from appointments.models import VisitAttachment

    attachment.summary_status = VisitAttachment.SummaryStatus.FAILED
    attachment.summary_error = (message or "Summary failed")[:500]
    attachment.save(
        update_fields=[
            "summary_status",
            "summary_error",
            "transcript_text",
            "summary_text",
        ]
    )


def _parse_next_visit_at(raw: Any):
    """Parse Gemini next_visit_at into timezone-aware datetime, or None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return None
    text = str(raw).strip()
    if not text or text.lower() in ("null", "none", "n/a", "-"):
        return None

    text = text.replace("Z", "").replace("z", "").strip()
    candidates: list[tuple[str, str]] = []
    if "T" in text or " " in text:
        candidates.append((text[:19], "%Y-%m-%dT%H:%M:%S"))
        candidates.append((text[:16].replace(" ", "T"), "%Y-%m-%dT%H:%M"))
        candidates.append((text[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"))
        candidates.append((text[:16].replace("T", " "), "%Y-%m-%d %H:%M"))
    candidates.append((text[:10], "%Y-%m-%d"))

    for value, fmt in candidates:
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=10, minute=0)
            return timezone.make_aware(dt, PK_TZ)
        except ValueError:
            continue
    return None


def _parse_gemini_payload(text: str) -> tuple[str, str, Any]:
    """Returns transcript, summary, next_visit_at raw."""
    raw = (text or "").strip()
    if not raw:
        return "", "Voice note se clear summary nahi ban saki.", None

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()

    try:
        data = json.loads(raw)
        transcript = str(data.get("transcript") or "").strip()
        summary = str(data.get("summary") or "").strip()
        next_visit = data.get("next_visit_at")
        if summary:
            return transcript, summary, next_visit
    except json.JSONDecodeError:
        pass

    return "", raw, None


def _apply_follow_up(attachment, follow_up_at) -> None:
    """Set follow_up_at; clear reminder flag if datetime changed."""
    prev = attachment.follow_up_at
    attachment.follow_up_at = follow_up_at
    if prev != follow_up_at:
        attachment.follow_up_reminder_sent_at = None


def _gemini_generate_content(
    *,
    api_key: str,
    model: str,
    parts: list[dict],
    timeout: int = 120,
) -> tuple[str | None, str | None]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }

    last_error = None
    for attempt, delay in enumerate(RETRY_BACKOFF_SECONDS):
        res = requests.post(
            url,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        if res.status_code in RETRYABLE_STATUS:
            last_error = f"Gemini failed ({res.status_code}): {res.text[:200]}"
            logger.warning(
                "Gemini %s attempt %s/%s: %s",
                model,
                attempt + 1,
                len(RETRY_BACKOFF_SECONDS),
                last_error,
            )
            if attempt < len(RETRY_BACKOFF_SECONDS) - 1:
                time.sleep(delay)
            continue

        if res.status_code >= 400:
            return None, f"Gemini failed ({res.status_code}): {res.text[:200]}"

        body = res.json()
        response_parts = (
            body.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        text = "".join(str(p.get("text") or "") for p in response_parts).strip()
        if not text:
            block = body.get("promptFeedback") or body.get("error") or body
            return None, f"Gemini returned empty content: {str(block)[:200]}"
        return text, None

    return None, last_error or f"Gemini model {model} unavailable (503/429)."


def _call_gemini(
    *,
    api_key: str,
    model: str,
    mime: str,
    audio_b64: str,
) -> tuple[str | None, str | None]:
    return _gemini_generate_content(
        api_key=api_key,
        model=model,
        parts=[
            {"text": PROMPT},
            {
                "inline_data": {
                    "mime_type": mime,
                    "data": audio_b64,
                }
            },
        ],
    )


def extract_follow_up_from_summary_text(summary: str):
    """Text-only Gemini extract of next_visit_at from edited summary. Returns aware dt or None."""
    api_key = _gemini_key()
    if not api_key or not (summary or "").strip():
        return None

    parts = [{"text": FOLLOW_UP_EXTRACT_PROMPT + summary.strip()}]
    last_error = None
    for model in _model_chain():
        text, err = _gemini_generate_content(
            api_key=api_key,
            model=model,
            parts=parts,
            timeout=60,
        )
        if err:
            last_error = err
            logger.warning("Follow-up extract via %s failed: %s", model, err)
            continue
        raw = (text or "").strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if fence:
            raw = fence.group(1).strip()
        try:
            data = json.loads(raw)
            return _parse_next_visit_at(data.get("next_visit_at"))
        except json.JSONDecodeError:
            return _parse_next_visit_at(raw)
    if last_error:
        logger.warning("Follow-up extract failed: %s", last_error)
    return None


def apply_follow_up_from_summary(attachment) -> None:
    """Re-extract follow_up_at from attachment.summary_text and save."""
    follow_up = extract_follow_up_from_summary_text(attachment.summary_text or "")
    _apply_follow_up(attachment, follow_up)
    attachment.save(
        update_fields=["follow_up_at", "follow_up_reminder_sent_at"]
    )


def generate_voice_summary(attachment_id: int) -> None:
    """Transcribe voice + produce Roman Urdu summary via Gemini. Soft-fails to failed."""
    from appointments.models import VisitAttachment

    try:
        att = VisitAttachment.objects.select_related("appointment").get(pk=attachment_id)
    except VisitAttachment.DoesNotExist:
        return

    if att.kind != VisitAttachment.Kind.VOICE:
        att.summary_status = VisitAttachment.SummaryStatus.SKIPPED
        att.save(update_fields=["summary_status"])
        return

    api_key = _gemini_key()
    if not api_key:
        _fail(att, "GEMINI_API_KEY is not configured on the server.")
        return

    if not att.file:
        _fail(att, "Voice file is missing.")
        return

    att.summary_status = VisitAttachment.SummaryStatus.PENDING
    att.summary_error = ""
    att.save(update_fields=["summary_status", "summary_error"])

    try:
        file_path = att.file.path
    except Exception:
        file_path = ""

    if not file_path or not Path(file_path).exists():
        _fail(att, "Voice file is not available on disk.")
        return

    mime = _audio_mime(file_path, att.mime_type)
    models = _model_chain()

    try:
        audio_b64 = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
        last_error = "Gemini summary failed."
        for model in models:
            text, err = _call_gemini(
                api_key=api_key,
                model=model,
                mime=mime,
                audio_b64=audio_b64,
            )
            if err:
                last_error = f"{model}: {err}"
                logger.warning(
                    "Voice summary model %s failed for attachment %s: %s",
                    model,
                    attachment_id,
                    err,
                )
                continue

            transcript, summary, next_raw = _parse_gemini_payload(text or "")
            follow_up = _parse_next_visit_at(next_raw)
            att.transcript_text = transcript
            att.summary_text = summary
            att.summary_status = VisitAttachment.SummaryStatus.READY
            att.summary_error = ""
            _apply_follow_up(att, follow_up)
            att.save(
                update_fields=[
                    "transcript_text",
                    "summary_text",
                    "summary_status",
                    "summary_error",
                    "follow_up_at",
                    "follow_up_reminder_sent_at",
                ]
            )
            return

        _fail(att, last_error)
    except requests.Timeout:
        logger.exception("Voice summary timed out for attachment %s", attachment_id)
        _fail(att, "Summary timed out. Try regenerate.")
    except Exception as exc:
        logger.exception("Voice summary failed for attachment %s", attachment_id)
        _fail(att, str(exc)[:500])
