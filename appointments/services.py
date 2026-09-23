from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from catalog.models import Clinic, DoctorAvailability, DoctorProfile
from patients.models import PatientProfile

from .models import Appointment

PAKISTAN_TZ = ZoneInfo("Asia/Karachi")


def pakistan_now() -> datetime:
    return timezone.now().astimezone(PAKISTAN_TZ)


def pakistan_today() -> date:
    return pakistan_now().date()


def pakistan_localtime(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, PAKISTAN_TZ)
    return dt.astimezone(PAKISTAN_TZ)


def format_clock(t: time) -> str:
    if t.hour == 0 and t.minute == 0:
        return "12:00 AM"
    return t.strftime("%I:%M %p").lstrip("0")


def format_end_clock(t: time) -> str:
    """Midnight means end of day."""
    if t.hour == 0 and t.minute == 0:
        return "12:00 AM"
    return format_clock(t)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def resolve_end_minutes(start: time, end: time) -> int:
    start_m = _minutes(start)
    end_m = _minutes(end)
    if end_m <= start_m:
        end_m += 24 * 60
    return end_m


def generate_slot_times(start: time, end: time, session_mins: int) -> list[time]:
    step = max(int(session_mins or 15), 5)
    start_m = _minutes(start)
    end_m = resolve_end_minutes(start, end)
    out: list[time] = []
    t = start_m
    while t + step <= end_m:
        out.append(time(hour=(t // 60) % 24, minute=t % 60))
        t += step
    if not out and start_m < end_m:
        out.append(start)
    return out


def generate_slots_for_windows(
    windows: list[dict],
    session_mins: int,
) -> list[time]:
    """Union of slots across multiple {start, end} windows (HH:MM:SS or time)."""
    slots: list[time] = []
    seen: set[str] = set()
    for win in windows:
        start = win["start"]
        end = win["end"]
        if isinstance(start, str):
            parts = [int(x) for x in start.split(":")[:3]]
            start = time(*parts)
        if isinstance(end, str):
            parts = [int(x) for x in end.split(":")[:3]]
            end = time(*parts)
        for slot in generate_slot_times(start, end, session_mins):
            key = slot.strftime("%H:%M:%S")
            if key not in seen:
                seen.add(key)
                slots.append(slot)
    slots.sort()
    return slots


def _window_dicts(day_rows: list[DoctorAvailability]) -> list[dict]:
    windows = []
    for row in day_rows:
        if not row.is_active:
            continue
        windows.append(
            {
                "start": row.start_time.strftime("%H:%M:%S"),
                "end": row.end_time.strftime("%H:%M:%S"),
            }
        )
    return windows


def _timing_label(windows: list[dict]) -> str:
    if not windows:
        return ""
    parts = []
    for win in windows:
        start_parts = [int(x) for x in win["start"].split(":")[:3]]
        end_parts = [int(x) for x in win["end"].split(":")[:3]]
        start_t = time(*start_parts)
        end_t = time(*end_parts)
        parts.append(f"{format_clock(start_t)} – {format_end_clock(end_t)}")
    return ", ".join(parts)


def upcoming_available_dates(
    doctor: DoctorProfile,
    *,
    clinic: Clinic | int | None = None,
    days_ahead: int = 42,
    limit: int = 42,
) -> list[dict]:
    """Return upcoming dates with open windows (weekly + date overrides)."""
    today = pakistan_today()
    qs = DoctorAvailability.objects.filter(doctor=doctor)
    if clinic is not None:
        clinic_id = clinic.pk if isinstance(clinic, Clinic) else int(clinic)
        qs = qs.filter(clinic_id=clinic_id)
    else:
        qs = qs.filter(clinic__isnull=False)

    slots = list(qs.order_by("specific_date", "weekday", "start_time"))
    by_weekday: dict[int, list[DoctorAvailability]] = {}
    by_date: dict[str, list[DoctorAvailability]] = {}
    for slot in slots:
        if slot.specific_date is not None:
            by_date.setdefault(slot.specific_date.isoformat(), []).append(slot)
        elif slot.is_active:
            by_weekday.setdefault(slot.weekday, []).append(slot)

    booked_times_by_date: dict[str, list[str]] = {}
    for appt in (
        Appointment.objects.filter(doctor=doctor, token_date__gte=today)
        .exclude(status=Appointment.Status.CANCELLED)
        .only("token_date", "scheduled_at")
    ):
        key = appt.token_date.isoformat()
        local_t = pakistan_localtime(appt.scheduled_at).time().strftime("%H:%M:%S")
        booked_times_by_date.setdefault(key, []).append(local_t)

    options: list[dict] = []
    for offset in range(0, days_ahead + 1):
        day = today + timedelta(days=offset)
        key = day.isoformat()

        if key in by_date:
            day_slots = by_date[key]
            windows = _window_dicts(day_slots)
            if not windows:
                # Explicit closed override (or empty active windows).
                continue
            clinic_id_for_day = day_slots[0].clinic_id if day_slots[0].clinic_id else None
        else:
            day_slots = by_weekday.get(day.weekday())
            if not day_slots:
                continue
            windows = _window_dicts(day_slots)
            if not windows:
                continue
            clinic_id_for_day = day_slots[0].clinic_id if day_slots[0].clinic_id else None

        booked_times = sorted(set(booked_times_by_date.get(key, [])))
        starts = [w["start"] for w in windows]
        ends = [w["end"] for w in windows]
        options.append(
            {
                "date": key,
                "label": day.strftime("%a %d %b %Y"),
                "start": min(starts),
                "end": max(ends) if "00:00:00" not in ends else "00:00:00",
                "timing": _timing_label(windows),
                "windows": windows,
                "booked_count": len(booked_times),
                "booked_times": booked_times,
                "clinic_id": clinic_id_for_day,
            }
        )
        if len(options) >= limit:
            break
    return options


def book_token(
    patient: PatientProfile,
    doctor: DoctorProfile,
    token_date: date,
    start_time: time | None = None,
    *,
    slot_time: time | None = None,
    clinic: Clinic | None = None,
    notes: str = "Booked via WhatsApp",
    payment_method: str = "",
    payment_status: str = "",
    payment_amount_expected=None,
    payment_amount_received=None,
    payment_reference: str = "",
    payment_ocr_raw: dict | None = None,
    payment_ocr_status: str = "",
    payment_verified_at=None,
) -> Appointment:
    with transaction.atomic():
        existing = (
            Appointment.objects.select_for_update()
            .filter(
                patient=patient,
                doctor=doctor,
                token_date=token_date,
                status=Appointment.Status.UPCOMING,
            )
            .first()
        )
        if existing:
            raise ValueError(
                f"You already have Token {existing.token_code} "
                f"with Dr. {doctor.full_name} on {token_date.strftime('%d %b %Y')}."
            )

        locked = (
            Appointment.objects.select_for_update()
            .filter(doctor=doctor, token_date=token_date)
            .aggregate(m=Max("token_number"))
        )
        next_token = (locked["m"] or 0) + 1

        day_start = start_time or time(9, 0)
        if slot_time is not None:
            base = datetime.combine(token_date, slot_time)
            if timezone.is_naive(base):
                base = timezone.make_aware(base, PAKISTAN_TZ)
            scheduled_at = base
            taken = (
                Appointment.objects.select_for_update()
                .filter(
                    doctor=doctor,
                    token_date=token_date,
                    scheduled_at=scheduled_at,
                )
                .exclude(status=Appointment.Status.CANCELLED)
                .exists()
            )
            if taken:
                raise ValueError("This time slot is already booked. Please pick another.")
        else:
            base = datetime.combine(token_date, day_start)
            if timezone.is_naive(base):
                base = timezone.make_aware(base, PAKISTAN_TZ)
            scheduled_at = base + timedelta(
                minutes=doctor.session_time * (next_token - 1)
            )

        create_kwargs: dict = {
            "patient": patient,
            "doctor": doctor,
            "clinic": clinic,
            "scheduled_at": scheduled_at,
            "token_date": token_date,
            "token_number": next_token,
            "status": Appointment.Status.UPCOMING,
            "notes": notes,
        }
        if payment_method:
            create_kwargs["payment_method"] = payment_method
        if payment_status:
            create_kwargs["payment_status"] = payment_status
        elif payment_method == Appointment.PaymentMethod.CASH_AT_CLINIC:
            create_kwargs["payment_status"] = Appointment.PaymentStatus.PENDING
        elif payment_method == Appointment.PaymentMethod.BANK_TRANSFER:
            create_kwargs["payment_status"] = Appointment.PaymentStatus.PAID
        if payment_amount_expected is not None:
            create_kwargs["payment_amount_expected"] = payment_amount_expected
        if payment_amount_received is not None:
            create_kwargs["payment_amount_received"] = payment_amount_received
        if payment_reference:
            create_kwargs["payment_reference"] = payment_reference
        if payment_ocr_raw is not None:
            create_kwargs["payment_ocr_raw"] = payment_ocr_raw
        if payment_ocr_status:
            create_kwargs["payment_ocr_status"] = payment_ocr_status
        elif payment_method == Appointment.PaymentMethod.CASH_AT_CLINIC:
            create_kwargs["payment_ocr_status"] = Appointment.PaymentOcrStatus.SKIPPED
        if payment_verified_at is not None:
            create_kwargs["payment_verified_at"] = payment_verified_at

        return Appointment.objects.create(**create_kwargs)


def queue_info(appointment: Appointment) -> dict:
    """Live token queue / ETA for a single appointment."""
    doctor = appointment.doctor
    day = appointment.token_date
    session_mins = max(int(doctor.session_time or 15), 1)
    today = pakistan_today()
    now = timezone.now()

    day_qs = Appointment.objects.filter(doctor=doctor, token_date=day).exclude(
        status=Appointment.Status.CANCELLED
    )

    # Currently serving = lowest remaining upcoming token for this doctor/day
    now_serving_appt = (
        day_qs.filter(status=Appointment.Status.UPCOMING)
        .order_by("token_number")
        .first()
    )
    now_serving_number = now_serving_appt.token_number if now_serving_appt else None
    now_serving_code = now_serving_appt.token_code if now_serving_appt else None

    completed_count = day_qs.filter(status=Appointment.Status.COMPLETED).count()
    total_upcoming = day_qs.filter(status=Appointment.Status.UPCOMING).count()

    people_ahead = day_qs.filter(
        status=Appointment.Status.UPCOMING,
        token_number__lt=appointment.token_number,
    ).count()

    status_value = str(appointment.status)
    wait_minutes = 0
    phase = "waiting"

    if appointment.status == Appointment.Status.COMPLETED:
        phase = "completed"
        message = (
            f"Token {appointment.token_code} is done. "
            "Thank you — hope you feel better soon."
        )
    elif appointment.status == Appointment.Status.CANCELLED:
        phase = "cancelled"
        message = f"Token {appointment.token_code} was cancelled."
    elif (
        now_serving_number is not None
        and now_serving_number == appointment.token_number
    ):
        phase = "now"
        wait_minutes = 0
        message = (
            f"It's your turn now — Token {appointment.token_code}. "
            "Please proceed to the doctor."
        )
    else:
        phase = "waiting"
        wait_minutes = people_ahead * session_mins
        serving_label = now_serving_code or "—"
        if wait_minutes <= 0:
            message = (
                f"Now serving {serving_label}. "
                f"Your token {appointment.token_code} is next — stay nearby."
            )
        elif wait_minutes < 60:
            message = (
                f"Now serving {serving_label}. "
                f"About {wait_minutes} min until Token {appointment.token_code}."
            )
        else:
            hours = wait_minutes // 60
            mins = wait_minutes % 60
            eta_label = f"{hours}h {mins}m" if mins else f"{hours}h"
            message = (
                f"Now serving {serving_label}. "
                f"About {eta_label} until Token {appointment.token_code}."
            )

    if day == today and phase in ("waiting", "now"):
        estimated = now + timedelta(minutes=wait_minutes)
    else:
        estimated = appointment.scheduled_at

    local_estimated = pakistan_localtime(estimated)
    approx = format_clock(local_estimated.time())
    date_label = appointment.token_date.strftime("%d %b %Y")

    return {
        "appointment_id": appointment.id,
        "token_code": appointment.token_code,
        "token_number": appointment.token_number,
        "token_date": appointment.token_date.isoformat(),
        "is_today": day == today,
        "position": appointment.token_number,
        "people_ahead": people_ahead,
        "wait_minutes": wait_minutes,
        "session_minutes": session_mins,
        "now_serving_number": now_serving_number,
        "now_serving_code": now_serving_code,
        "completed_count": completed_count,
        "upcoming_count": total_upcoming,
        "phase": phase,
        "estimated_at": estimated.isoformat(),
        "scheduled_at": appointment.scheduled_at.isoformat(),
        "approx_time": approx,
        "date_label": date_label,
        "doctor_name": doctor.full_name,
        "doctor_id": doctor.id,
        "clinic_id": appointment.clinic_id,
        "clinic_name": appointment.clinic.name if appointment.clinic_id else None,
        "status": status_value,
        "message": message,
        "updated_at": now.isoformat(),
    }


def lookup_patient_token(
    patient: PatientProfile,
    query: str,
    *,
    today_only: bool = True,
) -> Appointment | None:
    """Find a patient's appointment by token code (AH-003) or token number (3)."""
    raw = (query or "").strip().upper()
    if not raw:
        return None

    qs = Appointment.objects.filter(patient=patient).select_related("doctor", "clinic")
    if today_only:
        qs = qs.filter(token_date=pakistan_today())

    # Full token code e.g. AH-003 or AH003
    compact = raw.replace(" ", "")
    if "-" in compact or any(ch.isalpha() for ch in compact):
        for appt in qs.order_by("-token_date", "token_number"):
            code = appt.token_code.upper().replace(" ", "")
            if code == compact or code.replace("-", "") == compact.replace("-", ""):
                return appt

    # Numeric token number
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits:
        num = int(digits)
        match = qs.filter(token_number=num).order_by("-token_date", "token_number").first()
        if match:
            return match

    return None
