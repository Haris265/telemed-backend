"""OCR payment slips via Google Gemini — reference, date, amount checks."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PROMPT = """You are verifying a Pakistan bank / JazzCash / EasyPaisa payment transfer slip.
Read the image carefully.

Return ONLY valid JSON (no markdown fences) with exactly these keys:
{
  "reference": "unique transaction / invoice / reference / RR number from the slip",
  "date": "YYYY-MM-DD of the payment if visible, else null",
  "amount": 1234.56,
  "confidence": 0.0
}

Rules:
- amount must be a number (PKR), no currency symbol.
- reference must be the clearest unique code on the slip (not account title).
- If a field cannot be read, use null / "" and lower confidence.
- confidence is 0 to 1.
"""

MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.6-flash")
RETRYABLE_STATUS = {429, 503}
RETRY_BACKOFF_SECONDS = (1, 2, 4)
AMOUNT_TOLERANCE = Decimal("1.00")
DATE_WINDOW_DAYS = 2


@dataclass
class SlipOcrResult:
    ok: bool
    reference: str
    amount: Decimal | None
    payment_date: date | None
    confidence: float
    raw: dict[str, Any]
    error: str = ""


def _gemini_key() -> str:
    return (
        getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    ).strip()


def _ocr_model() -> str:
    return (
        getattr(settings, "GEMINI_OCR_MODEL", "")
        or os.getenv("GEMINI_OCR_MODEL", "")
        or getattr(settings, "GEMINI_SUMMARY_MODEL", "")
        or os.getenv("GEMINI_SUMMARY_MODEL", "gemini-3.5-flash-lite")
        or "gemini-3.5-flash-lite"
    ).strip()


def _model_chain() -> list[str]:
    primary = _ocr_model()
    chain: list[str] = []
    for name in (primary, *FALLBACK_MODELS):
        if name and name not in chain:
            chain.append(name)
    return chain


def _image_mime(path: str, declared: str = "") -> str:
    mime = (declared or "").strip().lower()
    if mime.startswith("image/"):
        return mime
    ext = Path(path).suffix.lower()
    return MIME_BY_EXT.get(ext, "image/jpeg")


def _parse_amount(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float, Decimal)):
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return None
    text = str(raw).strip().replace(",", "").replace("Rs", "").replace("PKR", "")
    text = re.sub(r"[^\d.]", "", text)
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if text.lower() in ("null", "none", "n/a", "-"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    # Try first 10 chars as ISO
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


def _gemini_generate_content(
    *,
    api_key: str,
    model: str,
    parts: list[dict],
    timeout: int = 90,
) -> tuple[str | None, str | None]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
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
                "Gemini OCR %s attempt %s/%s: %s",
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
            body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        )
        text = "".join(str(p.get("text") or "") for p in response_parts).strip()
        if not text:
            block = body.get("promptFeedback") or body.get("error") or body
            return None, f"Gemini returned empty content: {str(block)[:200]}"
        return text, None
    return None, last_error or f"Gemini model {model} unavailable (503/429)."


def _reference_looks_valid(reference: str) -> bool:
    ref = re.sub(r"\s+", "", reference or "")
    if len(ref) < 4:
        return False
    # Must have at least one digit or be a reasonable alphanumeric code
    if not re.search(r"[A-Za-z0-9]", ref):
        return False
    return bool(re.search(r"\d", ref) or len(ref) >= 6)


def _date_ok(payment_date: date | None, *, expected_date: date | None) -> bool:
    if payment_date is None:
        return False
    today = timezone.localdate()
    lo = today - timedelta(days=DATE_WINDOW_DAYS)
    hi = today + timedelta(days=DATE_WINDOW_DAYS)
    if lo <= payment_date <= hi:
        return True
    if expected_date and abs((payment_date - expected_date).days) <= DATE_WINDOW_DAYS:
        return True
    return False


def _amount_ok(received: Decimal | None, expected: Decimal) -> bool:
    if received is None:
        return False
    return abs(received - expected) <= AMOUNT_TOLERANCE


def verify_payment_slip(
    *,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    expected_amount: Decimal,
    expected_date: date | None = None,
    filename: str = "slip.jpg",
) -> SlipOcrResult:
    """Run Gemini OCR and validate reference, date, and amount."""
    api_key = _gemini_key()
    if not api_key:
        return SlipOcrResult(
            ok=False,
            reference="",
            amount=None,
            payment_date=None,
            confidence=0.0,
            raw={},
            error="GEMINI_API_KEY is not configured on the server.",
        )
    if not image_bytes:
        return SlipOcrResult(
            ok=False,
            reference="",
            amount=None,
            payment_date=None,
            confidence=0.0,
            raw={},
            error="Empty slip image.",
        )

    mime = mime_type if mime_type.startswith("image/") else _image_mime(filename, mime_type)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    parts = [
        {"text": PROMPT},
        {"inline_data": {"mime_type": mime, "data": b64}},
    ]

    last_error = "OCR failed."
    data: dict[str, Any] = {}
    for model in _model_chain():
        text, err = _gemini_generate_content(api_key=api_key, model=model, parts=parts)
        if err:
            last_error = err
            logger.warning("Slip OCR via %s failed: %s", model, err)
            continue
        data = _parse_payload(text or "")
        if data:
            break
        last_error = "Could not parse OCR JSON."
    else:
        return SlipOcrResult(
            ok=False,
            reference="",
            amount=None,
            payment_date=None,
            confidence=0.0,
            raw={},
            error=last_error,
        )

    reference = str(data.get("reference") or "").strip()
    amount = _parse_amount(data.get("amount"))
    payment_date = _parse_date(data.get("date"))
    try:
        confidence = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    checks = {
        "reference_ok": _reference_looks_valid(reference),
        "date_ok": _date_ok(payment_date, expected_date=expected_date),
        "amount_ok": _amount_ok(amount, Decimal(expected_amount)),
    }
    ok = all(checks.values())
    raw = {
        **data,
        "checks": checks,
        "expected_amount": str(expected_amount),
        "expected_date": expected_date.isoformat() if expected_date else None,
    }
    error = ""
    if not ok:
        failed = [k for k, v in checks.items() if not v]
        error = "OCR checks failed: " + ", ".join(failed)

    return SlipOcrResult(
        ok=ok,
        reference=reference,
        amount=amount,
        payment_date=payment_date,
        confidence=confidence,
        raw=raw,
        error=error,
    )


def verify_payment_slip_file(
    path: str,
    *,
    expected_amount: Decimal,
    expected_date: date | None = None,
    mime_type: str = "",
) -> SlipOcrResult:
    file_path = Path(path)
    if not file_path.is_file():
        return SlipOcrResult(
            ok=False,
            reference="",
            amount=None,
            payment_date=None,
            confidence=0.0,
            raw={},
            error="Slip file not found.",
        )
    return verify_payment_slip(
        image_bytes=file_path.read_bytes(),
        mime_type=mime_type or _image_mime(str(file_path)),
        expected_amount=expected_amount,
        expected_date=expected_date,
        filename=file_path.name,
    )
