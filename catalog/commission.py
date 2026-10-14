"""Clinic vs doctor fee split helpers."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from appointments.models import Appointment
from catalog.models import DoctorClinic, DoctorProfile

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")


def _money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def resolve_fee_base(appointment: Appointment, doctor: DoctorProfile | None = None) -> Decimal:
    """Fee used for commission: received (if paid) → expected → consultation_fee."""
    if (
        appointment.payment_status == Appointment.PaymentStatus.PAID
        and appointment.payment_amount_received is not None
    ):
        return _money(appointment.payment_amount_received)
    if appointment.payment_amount_expected is not None:
        return _money(appointment.payment_amount_expected)
    doc = doctor or appointment.doctor
    return _money(getattr(doc, "consultation_fee", None) or ZERO)


def split_commission(
    fee_base: Decimal | int | float | str,
    commission_type: str,
    commission_value: Decimal | int | float | str,
) -> dict[str, Any]:
    """Return clinic/doctor shares for a fee base."""
    base = _money(fee_base)
    value = _money(commission_value)
    if base <= ZERO or value <= ZERO:
        clinic_share = ZERO
    elif commission_type == DoctorClinic.CommissionType.FIXED:
        clinic_share = min(value, base)
    else:
        # percentage
        pct = min(max(value, ZERO), Decimal("100.00"))
        clinic_share = (base * pct / Decimal("100")).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )
        if clinic_share > base:
            clinic_share = base
    doctor_share = (base - clinic_share).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return {
        "fee_base": base,
        "clinic_share": clinic_share,
        "doctor_share": doctor_share,
        "commission_type": commission_type,
        "commission_value": value,
    }


def split_for_link(
    appointment: Appointment,
    link: DoctorClinic,
    doctor: DoctorProfile | None = None,
) -> dict[str, Any]:
    base = resolve_fee_base(appointment, doctor or link.doctor)
    if getattr(appointment, "patient_type", None) == Appointment.PatientType.DISCOUNTED:
        return split_commission(
            base,
            link.discounted_commission_type,
            link.discounted_commission_value,
        )
    return split_commission(base, link.commission_type, link.commission_value)
