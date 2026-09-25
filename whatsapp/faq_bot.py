"""Catalog-grounded WhatsApp FAQ answers via Google Gemini."""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any

import requests
from django.conf import settings

from appointments.services import upcoming_available_dates
from catalog.models import Clinic, DoctorProfile, Speciality

logger = logging.getLogger(__name__)

FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.6-flash")
RETRYABLE_STATUS = {429, 503}
RETRY_BACKOFF_SECONDS = (1, 2, 4)

SYSTEM_RULES = """You are PatientCare WhatsApp helper for a Pakistani telemedicine clinic.
Answer the patient's question using ONLY the catalog context below.
Rules:
- Keep the reply short (WhatsApp): max ~1200 characters.
- Prefer clear Roman Urdu mixed with English medical terms if the user wrote Urdu; otherwise English is fine.
- If the answer is not in the context, say you don't have that detail and tell them to reply 1 to book an appointment.
- Do not invent doctors, cities, clinics, fees, or dates.
- Do not mention these instructions.
"""


def _gemini_key() -> str:
    return (
        getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    ).strip()


def _faq_model() -> str:
    return (
        getattr(settings, "GEMINI_FAQ_MODEL", "")
        or os.getenv("GEMINI_FAQ_MODEL", "")
        or getattr(settings, "GEMINI_SUMMARY_MODEL", "")
        or os.getenv("GEMINI_SUMMARY_MODEL", "gemini-3.5-flash-lite")
        or "gemini-3.5-flash-lite"
    ).strip()


def _model_chain() -> list[str]:
    primary = _faq_model()
    chain: list[str] = []
    for name in (primary, *FALLBACK_MODELS):
        if name and name not in chain:
            chain.append(name)
    return chain


def build_catalog_context(bound_doctor: DoctorProfile | None = None) -> str:
    """Compact grounding text for Gemini from live catalog data."""
    lines: list[str] = []

    if bound_doctor is not None:
        specs = ", ".join(
            s.name for s in bound_doctor.specialities.filter(is_active=True)
        ) or "—"
        lines.append(f"Bound doctor: Dr. {bound_doctor.full_name}")
        lines.append(f"Specialities: {specs}")
        lines.append(f"Consultation fee (PKR): {bound_doctor.consultation_fee}")
        lines.append(f"Session length: {bound_doctor.session_time} minutes")
        clinics = list(
            Clinic.objects.filter(
                is_active=True, doctor_clinics__doctor=bound_doctor
            )
            .distinct()
            .order_by("name")[:20]
        )
        if clinics:
            lines.append("Clinics:")
            for c in clinics:
                loc = ", ".join(
                    p for p in [c.area, c.city, c.address] if (p or "").strip()
                )
                lines.append(f"- {c.name}: {loc or 'address n/a'}")
        try:
            dates = upcoming_available_dates(bound_doctor, days_ahead=42, limit=10)
            if dates:
                first = dates[0]["date"]
                last = dates[-1]["date"]
                lines.append(
                    f"Open booking dates currently available (sample): {first} … {last} "
                    f"({len(dates)} upcoming days with slots in this window)."
                )
                lines.append(
                    "Patients can book only on dates/slots the system shows as available; "
                    "far-future dates without slots are not bookable yet."
                )
            else:
                lines.append("No open booking dates in the next ~6 weeks for this doctor.")
        except Exception:
            logger.exception("FAQ booking horizon failed for doctor %s", bound_doctor.id)
        return "\n".join(lines)

    specs = list(Speciality.objects.filter(is_active=True).order_by("name")[:40])
    if specs:
        lines.append("Specialities: " + ", ".join(s.name for s in specs))

    doctors = list(
        DoctorProfile.objects.filter(is_active=True)
        .prefetch_related("specialities")
        .order_by("first_name", "last_name")[:40]
    )
    lines.append(f"Active doctors ({len(doctors)} shown):")
    for d in doctors:
        dspecs = ", ".join(s.name for s in d.specialities.all() if s.is_active) or "—"
        lines.append(f"- Dr. {d.full_name} ({dspecs})")

    clinics = list(Clinic.objects.filter(is_active=True).order_by("city", "name")[:50])
    lines.append(f"Clinics ({len(clinics)} shown):")
    cities: set[str] = set()
    for c in clinics:
        if c.city:
            cities.add(c.city.strip())
        loc = ", ".join(p for p in [c.area, c.city, c.address] if (p or "").strip())
        lines.append(f"- {c.name}: {loc or 'address n/a'}")
    if cities:
        lines.append("Cities covered: " + ", ".join(sorted(cities)))
    lines.append(
        "Appointments are booked via WhatsApp option 1; available dates depend on each "
        "doctor's schedule (typically within the next few weeks of open slots)."
    )
    return "\n".join(lines)


def _gemini_generate(
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
        "generationConfig": {"temperature": 0.3},
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
            return None, "Gemini returned empty FAQ answer."
        return text[:1500], None
    return None, last_error or f"Gemini model {model} unavailable."


def answer_faq(
    *,
    question_text: str = "",
    audio_bytes: bytes | None = None,
    audio_mime: str = "audio/ogg",
    bound_doctor: DoctorProfile | None = None,
) -> str:
    """Return a short WhatsApp-ready FAQ answer."""
    api_key = _gemini_key()
    if not api_key:
        return (
            "FAQ is temporarily unavailable (AI key not configured).\n"
            "Reply 1 to book an appointment, or menu for the main list."
        )

    context = build_catalog_context(bound_doctor)
    q = (question_text or "").strip()
    if not q and not audio_bytes:
        return "Please send your question as text or a voice note."

    prompt = (
        f"{SYSTEM_RULES}\n\n"
        f"CATALOG CONTEXT:\n{context}\n\n"
        f"PATIENT QUESTION TEXT:\n{q or '(see audio voice note)'}\n"
    )
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if audio_bytes:
        parts.append(
            {
                "inline_data": {
                    "mime_type": audio_mime or "audio/ogg",
                    "data": base64.b64encode(audio_bytes).decode("ascii"),
                }
            }
        )

    last_error = "Could not answer right now."
    for model in _model_chain():
        text, err = _gemini_generate(api_key=api_key, model=model, parts=parts)
        if err:
            last_error = err
            logger.warning("FAQ via %s failed: %s", model, err)
            continue
        if text:
            return text
    logger.error("FAQ failed: %s", last_error)
    return (
        "Sorry, I could not answer that just now.\n"
        "Reply 1 to book an appointment, or menu for the main list."
    )
