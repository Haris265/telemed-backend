from __future__ import annotations

from dataclasses import dataclass

from catalog.models import Speciality

DISCLAIMER = (
    "This tool offers general guidance only and is not a medical diagnosis. "
    "If symptoms are severe or worsening, seek emergency care immediately."
)

EMERGENCY_KEYWORDS = (
    "unconscious",
    "not breathing",
    "can't breathe",
    "cannot breathe",
    "severe bleeding",
    "heavy bleeding",
    "heart attack",
    "stroke",
    "seizure",
    "choking",
)

URGENT_KEYWORDS = (
    "high fever",
    "very high fever",
    "severe pain",
    "intense pain",
    "sudden weakness",
    "confusion",
    "vomiting blood",
    "blood in stool",
)

SPECIALITY_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("chest pain", "heart", "palpitation", "cardiac", "breathless", "breathlessness"),
        ("cardio", "heart"),
    ),
    (
        ("skin", "rash", "itch", "itchy", "acne", "eczema", "hives"),
        ("dermat", "skin"),
    ),
    (
        ("bone", "joint", "back pain", "knee", "fracture", "sprain", "arthritis"),
        ("ortho", "physio", "bone", "joint"),
    ),
    (
        ("headache", "migraine", "dizzy", "dizziness", "vertigo"),
        ("neuro", "brain", "head"),
    ),
    (
        ("stomach", "abdominal", "nausea", "vomit", "diarrhea", "constipation", "acid"),
        ("gastro", "stomach", "digest"),
    ),
    (
        ("eye", "vision", "blurry", "red eye"),
        ("ophthal", "eye"),
    ),
    (
        ("ear", "nose", "throat", "sinus", "cold", "cough", "sore throat", "runny nose"),
        ("ent", "ear", "nose", "throat"),
    ),
    (
        ("fever", "flu", "fatigue", "weakness", "general"),
        ("general", "medicine", "physician", "family"),
    ),
    (
        ("child", "baby", "infant", "pediatric"),
        ("pediat", "child"),
    ),
    (
        ("pregnant", "pregnancy", "prenatal"),
        ("gyn", "obstet", "women"),
    ),
    (
        ("urine", "urinary", "kidney", "bladder"),
        ("urolog", "nephro", "kidney"),
    ),
    (
        ("anxiety", "depression", "stress", "mental", "sleep"),
        ("psych", "mental"),
    ),
]


class SymptomCheckUrgency:
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


@dataclass
class TriageResult:
    urgency: str
    summary: str
    recommended_specialities: list[Speciality]


def _detect_urgency(text: str) -> str:
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text:
            return SymptomCheckUrgency.EMERGENCY
    for keyword in URGENT_KEYWORDS:
        if keyword in text:
            return SymptomCheckUrgency.URGENT
    return SymptomCheckUrgency.ROUTINE


def _score_specialities(text: str, active: list[Speciality]) -> dict[int, int]:
    scores: dict[int, int] = {}

    for keywords, patterns in SPECIALITY_RULES:
        matched = any(keyword in text for keyword in keywords)
        if not matched:
            continue
        for spec in active:
            name_lower = spec.name.lower()
            if any(pattern in name_lower for pattern in patterns):
                scores[spec.id] = scores.get(spec.id, 0) + 1

    for spec in active:
        name_lower = spec.name.lower()
        if name_lower in text or any(part in text for part in name_lower.split() if len(part) > 3):
            scores[spec.id] = scores.get(spec.id, 0) + 2

    return scores


def _fallback_specialities(active: list[Speciality]) -> list[Speciality]:
    for spec in active:
        if "general" in spec.name.lower():
            return [spec]
    return active[:1]


def _build_summary(urgency: str, recommended: list[Speciality]) -> str:
    names = ", ".join(spec.name for spec in recommended)
    if urgency == SymptomCheckUrgency.EMERGENCY:
        return (
            "Your symptoms may need immediate emergency care. "
            "Visit the nearest ER or call emergency services. "
            f"For follow-up, these specialities may help: {names}."
        )
    if urgency == SymptomCheckUrgency.URGENT:
        return (
            f"Your symptoms suggest you should see a doctor soon. "
            f"Recommended specialities: {names}."
        )
    if recommended:
        return f"Based on your symptoms, consider booking with: {names}."
    return (
        "We could not match your symptoms to a specific speciality. "
        "Please describe more details or book with any available doctor."
    )


def triage_symptoms(symptoms_text: str) -> TriageResult:
    text = (symptoms_text or "").lower().strip()
    active = list(Speciality.objects.filter(is_active=True).order_by("name"))
    urgency = _detect_urgency(text)
    scores = _score_specialities(text, active)

    if scores:
        top_ids = sorted(scores.keys(), key=lambda spec_id: scores[spec_id], reverse=True)[:3]
        recommended = sorted(
            [spec for spec in active if spec.id in top_ids],
            key=lambda spec: scores[spec.id],
            reverse=True,
        )
    else:
        recommended = _fallback_specialities(active)

    summary = _build_summary(urgency, recommended)
    return TriageResult(
        urgency=urgency,
        summary=summary,
        recommended_specialities=recommended,
    )
