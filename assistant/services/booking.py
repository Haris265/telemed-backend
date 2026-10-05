"""Cash booking wrapper around appointments.services.book_token."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from appointments.models import Appointment
from appointments.services import book_token
from catalog.models import Clinic, DoctorProfile
from patients.models import PatientProfile


def book_cash_appointment(
    *,
    patient: PatientProfile,
    doctor: DoctorProfile,
    clinic: Clinic,
    token_date: date,
    slot_time: time,
) -> Appointment:
    fee = doctor.consultation_fee or Decimal("0")
    return book_token(
        patient,
        doctor,
        token_date,
        slot_time=slot_time,
        clinic=clinic,
        notes="Booked via clinic assistant",
        payment_method=Appointment.PaymentMethod.CASH_AT_CLINIC,
        payment_status=Appointment.PaymentStatus.PENDING,
        payment_amount_expected=fee if fee > 0 else None,
        payment_ocr_status=Appointment.PaymentOcrStatus.SKIPPED,
    )
