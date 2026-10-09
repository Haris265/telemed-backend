"""Slot helpers wrapping appointments.services."""

from __future__ import annotations

from datetime import date, datetime, time

from appointments.services import (
    format_clock,
    open_slot_options,
    pakistan_localtime,
    pakistan_today,
    upcoming_available_dates,
)
from catalog.models import Clinic, DoctorProfile


def next_available_dates(
    doctor: DoctorProfile,
    clinic: Clinic,
    *,
    days_ahead: int = 14,
    limit: int = 5,
) -> list[dict]:
    options = upcoming_available_dates(
        doctor,
        clinic=clinic,
        days_ahead=days_ahead,
        limit=days_ahead + 1,
    )
    out = []
    for opt in options:
        open_slots = open_slot_options(doctor, opt)
        if not open_slots:
            continue
        out.append(
            {
                "date": opt["date"],
                "date_label": opt["label"],
                "open_slot_count": len(open_slots),
                "timing": opt.get("timing") or "",
            }
        )
        if len(out) >= limit:
            break
    return out


def open_times_for_date(
    doctor: DoctorProfile,
    clinic: Clinic,
    token_date: date,
    *,
    max_slots: int = 24,
    now: datetime | None = None,
) -> list[dict]:
    today = pakistan_today()
    days_ahead = max((token_date - today).days + 1, 1)
    options = upcoming_available_dates(
        doctor,
        clinic=clinic,
        days_ahead=days_ahead,
        limit=60,
    )
    key = token_date.isoformat()
    option = next((o for o in options if o["date"] == key), None)
    if not option:
        return []
    return open_slot_options(doctor, option, now=now)[:max_slots]


def sample_next_slots(
    doctor: DoctorProfile,
    clinic: Clinic,
    *,
    dates: int = 2,
    slots_per_date: int = 3,
    days_ahead: int = 14,
    now: datetime | None = None,
) -> list[dict]:
    options = upcoming_available_dates(
        doctor,
        clinic=clinic,
        days_ahead=days_ahead,
        limit=dates,
    )
    samples = []
    for opt in options:
        open_slots = open_slot_options(doctor, opt, now=now)[:slots_per_date]
        if not open_slots:
            continue
        samples.append(
            {
                "date": opt["date"],
                "date_label": opt["label"],
                "times": [s["label"] for s in open_slots],
                "time_values": [s["time"] for s in open_slots],
            }
        )
    return samples


def parse_slot_time(value: str) -> time:
    parts = [int(x) for x in value.split(":")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return time(*parts)


def label_slot(value: str | time) -> str:
    if isinstance(value, str):
        value = parse_slot_time(value)
    return format_clock(value)


def label_datetime(dt: datetime) -> str:
    local = pakistan_localtime(dt)
    return format_clock(local.time())
