"""Which clinics appear in the parent chatbot."""

from __future__ import annotations

from catalog.models import Clinic

from .models import ClinicAssistantConfig


def eligible_clinics_qs():
    """Active clinics with an enabled assistant config."""
    enabled_ids = ClinicAssistantConfig.objects.filter(is_enabled=True).values_list(
        "clinic_id", flat=True
    )
    return Clinic.objects.filter(is_active=True, id__in=enabled_ids).order_by("name", "id")


def clinic_list_rows() -> list[dict]:
    rows = []
    for i, clinic in enumerate(eligible_clinics_qs(), start=1):
        rows.append(
            {
                "n": i,
                "clinic_id": clinic.id,
                "name": clinic.name,
                "area": clinic.area or "",
                "address": clinic.address or "",
                "city": clinic.city or "",
                "phone": clinic.phone or "",
            }
        )
    return rows


def is_clinic_eligible(clinic_id: int) -> bool:
    return eligible_clinics_qs().filter(pk=clinic_id).exists()


def resolve_eligible_clinic(clinic_id: int) -> Clinic | None:
    return eligible_clinics_qs().filter(pk=clinic_id).first()
