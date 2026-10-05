"""Patient lookup / create by phone variants."""

from __future__ import annotations

from patients.models import PatientProfile
from patients.serializers import clean_name

from assistant.phone import canonical_phone, phone_variants


def find_patient_by_phone(raw_phone: str) -> PatientProfile | None:
    canonical = canonical_phone(raw_phone)
    if not canonical:
        return None
    return (
        PatientProfile.objects.filter(phone__in=phone_variants(canonical))
        .order_by("-id")
        .first()
    )


def get_or_create_patient(*, phone: str, name: str) -> PatientProfile:
    canonical = canonical_phone(phone)
    existing = find_patient_by_phone(canonical)
    cleaned = clean_name(name) or ""
    if existing:
        if cleaned and not existing.name:
            existing.name = cleaned
            existing.save(update_fields=["name", "updated_at"])
        return existing
    return PatientProfile.objects.create(phone=canonical, name=cleaned or "Patient")
