"""Clinic-admin doctor detail enrichment helpers."""

from __future__ import annotations

from decimal import Decimal

from appointments.models import Appointment
from appointments.services import open_slot_options, upcoming_available_dates
from catalog.commission import ZERO, _money, split_for_link
from catalog.models import Clinic, DoctorAvailability, DoctorClinic, DoctorProfile

WEEKDAY_LABELS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def clinic_link_for(doctor: DoctorProfile, clinic: Clinic) -> DoctorClinic | None:
    return (
        DoctorClinic.objects.filter(doctor=doctor, clinic=clinic)
        .select_related("doctor", "clinic")
        .first()
    )


def build_availability(doctor: DoctorProfile, clinic: Clinic) -> dict:
    qs = DoctorAvailability.objects.filter(
        doctor=doctor, clinic=clinic, is_active=True
    ).order_by("specific_date", "weekday", "start_time")
    weekly = []
    overrides = []
    for row in qs:
        item = {
            "id": row.id,
            "weekday": row.weekday,
            "weekday_label": WEEKDAY_LABELS.get(row.weekday, str(row.weekday)),
            "start_time": row.start_time.strftime("%H:%M:%S"),
            "end_time": row.end_time.strftime("%H:%M:%S"),
            "is_active": row.is_active,
        }
        if row.specific_date is None:
            weekly.append(item)
        else:
            item["specific_date"] = row.specific_date.isoformat()
            overrides.append(item)
    return {"weekly": weekly, "date_overrides": overrides}


def build_upcoming_slots(
    doctor: DoctorProfile, clinic: Clinic, *, days: int = 7, max_times: int = 4
) -> list[dict]:
    options = upcoming_available_dates(
        doctor, clinic=clinic, days_ahead=days, limit=days
    )
    result = []
    for opt in options:
        slots = open_slot_options(doctor, opt)[:max_times]
        if not slots:
            continue
        result.append(
            {
                "date": opt["date"],
                "date_label": opt.get("label") or opt["date"],
                "times": [s.get("label") or s["time"][:5] for s in slots],
            }
        )
    return result


def appointment_row(appt: Appointment, link: DoctorClinic) -> dict:
    split = split_for_link(appt, link)
    return {
        "id": appt.id,
        "scheduled_at": appt.scheduled_at.isoformat() if appt.scheduled_at else None,
        "token_date": appt.token_date.isoformat() if appt.token_date else None,
        "token_number": appt.token_number,
        "status": appt.status,
        "patient_id": appt.patient_id,
        "patient_name": appt.patient.name if appt.patient_id else "",
        "patient_phone": appt.patient.phone if appt.patient_id else "",
        "fee_base": str(split["fee_base"]),
        "payment_status": appt.payment_status,
        "payment_method": appt.payment_method or "",
        "clinic_share": str(split["clinic_share"]),
        "doctor_share": str(split["doctor_share"]),
        "commission_type": split["commission_type"],
        "commission_value": str(split["commission_value"]),
    }


def build_detail_payload(doctor: DoctorProfile, clinic: Clinic) -> dict:
    link = clinic_link_for(doctor, clinic)
    if link is None:
        raise DoctorClinic.DoesNotExist

    appts = list(
        Appointment.objects.filter(doctor=doctor, clinic=clinic)
        .select_related("patient")
        .order_by("-scheduled_at", "-id")[:50]
    )

    gross = ZERO
    clinic_total = ZERO
    doctor_total = ZERO
    upcoming = completed = cancelled = 0
    patient_visits: dict[int, dict] = {}

    for appt in appts:
        row = appointment_row(appt, link)
        if appt.status == Appointment.Status.UPCOMING:
            upcoming += 1
        elif appt.status == Appointment.Status.COMPLETED:
            completed += 1
            gross += _money(row["fee_base"])
            clinic_total += _money(row["clinic_share"])
            doctor_total += _money(row["doctor_share"])
        elif appt.status == Appointment.Status.CANCELLED:
            cancelled += 1

        pid = appt.patient_id
        if pid:
            entry = patient_visits.setdefault(
                pid,
                {
                    "id": pid,
                    "uuid": str(appt.patient.uuid),
                    "name": appt.patient.name,
                    "phone": appt.patient.phone,
                    "visit_count": 0,
                },
            )
            entry["visit_count"] += 1

    patients = sorted(
        patient_visits.values(), key=lambda p: (-p["visit_count"], p["name"])
    )

    return {
        "clinic_link": {
            "id": link.id,
            "is_primary": link.is_primary,
            "commission_type": link.commission_type,
            "commission_value": str(link.commission_value),
            "commission_updated_at": (
                link.commission_updated_at.isoformat()
                if link.commission_updated_at
                else None
            ),
        },
        "availability": build_availability(doctor, clinic),
        "upcoming_slots": build_upcoming_slots(doctor, clinic),
        "stats": {
            "patient_count": len(patients),
            "upcoming_count": upcoming,
            "completed_count": completed,
            "cancelled_count": cancelled,
            "gross_fees": str(gross),
            "clinic_commission_total": str(clinic_total),
            "doctor_earnings_total": str(doctor_total),
        },
        "patients": patients,
        "appointments": [appointment_row(a, link) for a in appts],
    }
