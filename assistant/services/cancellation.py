"""Patient-scoped cancellation using appointments.services.cancel_appointment_by_patient."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings

from appointments.models import Appointment
from appointments.services import (
    CancellationNotAllowed,
    can_cancel_appointment,
    cancel_appointment_by_patient,
    format_clock,
    pakistan_localtime,
)
from catalog.models import Clinic
from patients.models import PatientProfile

from assistant.phone import phone_variants


def min_lead() -> timedelta:
    minutes = int(getattr(settings, "ASSISTANT_CANCEL_MIN_LEAD_MINUTES", 60))
    return timedelta(minutes=minutes)


def cancel_for_patient(
    appointment_id: int,
    *,
    patient: PatientProfile,
    clinic: Clinic,
    now: datetime | None = None,
) -> Appointment:
    return cancel_appointment_by_patient(
        appointment_id,
        patient,
        clinic,
        min_lead=min_lead(),
        now=now,
    )


def cancel_flags(
    appointment: Appointment,
    *,
    now: datetime | None = None,
) -> dict:
    allowed, cancel_until = can_cancel_appointment(
        appointment, min_lead=min_lead(), now=now
    )
    cancel_until_label = None
    if cancel_until is not None:
        local = pakistan_localtime(cancel_until)
        cancel_until_label = format_clock(local.time())
    return {
        "can_cancel": allowed,
        "cancel_until": cancel_until_label,
    }


__all__ = [
    "CancellationNotAllowed",
    "cancel_for_patient",
    "cancel_flags",
    "min_lead",
    "phone_variants",
]
