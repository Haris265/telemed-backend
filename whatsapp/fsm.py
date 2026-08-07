import logging
import random
import re
import string
from datetime import date, time

from django.core.cache import cache

from appointments.models import Appointment
from appointments.services import (
    book_token,
    format_clock,
    generate_slots_for_windows,
    pakistan_now,
    pakistan_today,
    upcoming_available_dates,
)
from catalog.models import Clinic, DoctorAvailability, DoctorProfile, Speciality
from patients.models import PatientProfile

from .models import WhatsAppSession

logger = logging.getLogger(__name__)

MENU_TEXT = (
    "Welcome to Telemed.\n\n"
    "Reply with:\n"
    "1. Request OTP for Login\n"
    "2. Book an appointment\n"
    "3. View My Appointments"
)


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _clean_patient_name(value: str) -> str:
    name = re.sub(r"\s+", " ", (value or "").strip())
    if len(name) < 2:
        return ""
    # Reject pure digits / phone-like placeholders
    if name.isdigit():
        return ""
    return name[:150]


def _get_or_create_session(phone: str) -> WhatsAppSession:
    session, _ = WhatsAppSession.objects.get_or_create(phone=phone)
    return session


def _message_text(msg: dict) -> str:
    if msg.get("type") == "text":
        return (msg.get("text") or {}).get("body", "").strip()
    if msg.get("type") == "button":
        return ((msg.get("button") or {}).get("text") or "").strip()
    if msg.get("type") == "interactive":
        interactive = msg.get("interactive") or {}
        if interactive.get("type") == "button_reply":
            return ((interactive.get("button_reply") or {}).get("title") or "").strip()
        if interactive.get("type") == "list_reply":
            return ((interactive.get("list_reply") or {}).get("title") or "").strip()
    return ""


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _norm_name(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"^dr\.?\s*", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _parse_choice_index(text: str, count: int) -> int | None:
    raw = text.strip()
    if not raw.isdigit():
        return None
    idx = int(raw)
    if 1 <= idx <= count:
        return idx - 1
    return None


def _match_by_name(text: str, items: list, get_name) -> list:
    needle = _norm_name(text)
    if len(needle) < 2:
        return []
    exact = [item for item in items if _norm_name(get_name(item)) == needle]
    if exact:
        return exact
    return [item for item in items if needle in _norm_name(get_name(item))]


def _active_specialities():
    return list(Speciality.objects.filter(is_active=True).order_by("name"))


def _active_doctors_for_speciality(speciality_id: int):
    return list(
        DoctorProfile.objects.filter(
            is_active=True,
            specialities__id=speciality_id,
        )
        .distinct()
        .order_by("first_name", "last_name")
    )


def _active_doctors_all():
    return list(
        DoctorProfile.objects.filter(is_active=True).order_by("first_name", "last_name")
    )


def _doctor_clinics(doctor: DoctorProfile) -> list[Clinic]:
    return list(
        Clinic.objects.filter(
            is_active=True,
            doctor_clinics__doctor=doctor,
        )
        .distinct()
        .order_by("name")
    )


def _format_availability(doctor: DoctorProfile, clinic: Clinic | None = None) -> str:
    qs = DoctorAvailability.objects.filter(
        doctor=doctor, is_active=True, clinic__isnull=False
    )
    if clinic is not None:
        qs = qs.filter(clinic=clinic)
    slots = list(qs.order_by("weekday", "start_time"))
    if not slots:
        return "Weekly schedule: Not set yet."

    lines = ["Weekly schedule (Pakistan time):"]
    for slot in slots:
        clinic_label = f" @ {slot.clinic.name}" if slot.clinic_id and clinic is None else ""
        lines.append(
            f"• {slot.get_weekday_display()}{clinic_label}: "
            f"{format_clock(slot.start_time)} – {format_clock(slot.end_time)}"
        )
    return "\n".join(lines)


def _upcoming_available_dates(
    doctor: DoctorProfile,
    clinic: Clinic,
    *,
    days_ahead: int = 21,
    limit: int = 10,
) -> list[dict]:
    return upcoming_available_dates(
        doctor, clinic=clinic, days_ahead=days_ahead, limit=limit
    )


def _format_clinics(clinics: list[Clinic]) -> str:
    lines = ["Select a clinic (reply with number):"]
    for i, c in enumerate(clinics, start=1):
        area = ", ".join(p for p in [c.area, c.city] if p)
        suffix = f" — {area}" if area else ""
        lines.append(f"{i}. {c.name}{suffix}")
    lines.append("\nReply 0 to cancel.")
    return "\n".join(lines)


def _format_date_options(
    doctor: DoctorProfile,
    clinic: Clinic,
    options: list[dict],
) -> str:
    lines = [
        f"Dr. {doctor.full_name}",
        f"Clinic: {clinic.name}",
        _format_availability(doctor, clinic),
        "",
        "Select a date (reply with number):",
    ]
    for i, opt in enumerate(options, start=1):
        lines.append(f"{i}. {opt['label']} ({opt['timing']})")
    lines.append("\nReply 0 to cancel.")
    return "\n".join(lines)


def _open_slot_options(doctor: DoctorProfile, option: dict) -> list[dict]:
    windows = option.get("windows") or [
        {"start": option["start"], "end": option["end"]}
    ]
    booked = set(option.get("booked_times") or [])
    is_today = option["date"] == pakistan_today().isoformat()
    now = pakistan_now().time()
    slots = []
    for slot in generate_slots_for_windows(windows, doctor.session_time):
        key = slot.strftime("%H:%M:%S")
        if key in booked:
            continue
        if is_today and slot <= now:
            continue
        slots.append(
            {
                "time": key,
                "label": format_clock(slot),
            }
        )
    return slots


def _format_slot_options(options: list[dict]) -> str:
    lines = ["Select a time slot (Pakistan time) — reply with number:"]
    for i, opt in enumerate(options, start=1):
        lines.append(f"{i}. {opt['label']}")
    lines.append("\nReply 0 to cancel.")
    return "\n".join(lines)


def _format_specialities(items: list[Speciality]) -> str:
    lines = [
        "Select a speciality — reply with number OR name.",
        "Or type a doctor name (e.g. Ayesha Khan) to book directly.",
        "",
    ]
    for i, s in enumerate(items, start=1):
        lines.append(f"{i}. {s.name}")
    lines.append("\nReply 0 to cancel.")
    return "\n".join(lines)


def _format_doctors(items: list[DoctorProfile]) -> str:
    lines = ["Select a doctor — reply with number OR name:"]
    for i, d in enumerate(items, start=1):
        lines.append(f"{i}. Dr. {d.full_name} ({d.session_time} min)")
    lines.append("\nReply 0 to cancel.")
    return "\n".join(lines)


def _format_appointments(patient: PatientProfile) -> str:
    today = pakistan_today()
    appts = (
        Appointment.objects.filter(
            patient=patient,
            status=Appointment.Status.UPCOMING,
            token_date__gte=today,
        )
        .select_related("doctor", "clinic")
        .order_by("token_date", "token_number")[:10]
    )
    if not appts:
        return "No upcoming appointments."

    from zoneinfo import ZoneInfo

    karachi = ZoneInfo("Asia/Karachi")
    lines = ["Your upcoming appointments:"]
    for a in appts:
        when = a.token_date.strftime("%d %b %Y")
        local_t = a.scheduled_at.astimezone(karachi).time()
        clinic = f" @ {a.clinic.name}" if a.clinic_id else ""
        lines.append(
            f"• Token {a.token_code} — Dr. {a.doctor.full_name}{clinic} — "
            f"{when} {format_clock(local_t)}"
        )
    return "\n".join(lines)


def _reset_to_menu(session: WhatsAppSession) -> None:
    session.state = WhatsAppSession.State.MENU
    session.context = {}
    session.save(update_fields=["state", "context", "updated_at"])


def _start_booking(session: WhatsAppSession, client, phone: str) -> None:
    specialities = _active_specialities()
    if not specialities:
        client.send_text(phone, "No specialities available right now. Please try later.")
        _reset_to_menu(session)
        return
    session.state = WhatsAppSession.State.AWAITING_SPECIALITY
    session.context = {"speciality_ids": [s.id for s in specialities]}
    session.save(update_fields=["state", "context", "updated_at"])
    client.send_text(phone, _format_specialities(specialities))


def _offer_doctors(
    session: WhatsAppSession,
    client,
    phone: str,
    speciality: Speciality,
    doctors: list[DoctorProfile],
) -> None:
    if not doctors:
        client.send_text(
            phone,
            f"No doctors available for {speciality.name} right now.\n\n{MENU_TEXT}",
        )
        _reset_to_menu(session)
        return
    session.state = WhatsAppSession.State.AWAITING_DOCTOR
    session.context = {
        "speciality_id": speciality.id,
        "doctor_ids": [d.id for d in doctors],
    }
    session.save(update_fields=["state", "context", "updated_at"])
    client.send_text(phone, f"{speciality.name}\n\n{_format_doctors(doctors)}")


def _prompt_clinic_selection(
    session: WhatsAppSession,
    client,
    phone: str,
    doctor: DoctorProfile,
) -> None:
    clinics = _doctor_clinics(doctor)
    if not clinics:
        client.send_text(
            phone,
            f"Dr. {doctor.full_name} has no clinic schedule yet.\n\n{MENU_TEXT}",
        )
        _reset_to_menu(session)
        return
    if len(clinics) == 1:
        _prompt_date_selection(session, client, phone, doctor, clinics[0])
        return
    session.state = WhatsAppSession.State.AWAITING_CLINIC
    session.context = {
        "doctor_id": doctor.id,
        "clinic_ids": [c.id for c in clinics],
    }
    session.save(update_fields=["state", "context", "updated_at"])
    client.send_text(
        phone,
        f"Dr. {doctor.full_name}\n\n{_format_clinics(clinics)}",
    )


def _prompt_date_selection(
    session: WhatsAppSession,
    client,
    phone: str,
    doctor: DoctorProfile,
    clinic: Clinic,
) -> None:
    options = _upcoming_available_dates(doctor, clinic)
    if not options:
        client.send_text(
            phone,
            f"Dr. {doctor.full_name} has no upcoming dates at {clinic.name}.\n\n{MENU_TEXT}",
        )
        _reset_to_menu(session)
        return
    session.state = WhatsAppSession.State.AWAITING_DATE
    session.context = {
        "doctor_id": doctor.id,
        "clinic_id": clinic.id,
        "date_options": options,
    }
    session.save(update_fields=["state", "context", "updated_at"])
    client.send_text(phone, _format_date_options(doctor, clinic, options))


def _prompt_slot_selection(
    session: WhatsAppSession,
    client,
    phone: str,
    doctor: DoctorProfile,
    clinic: Clinic,
    option: dict,
) -> None:
    slots = _open_slot_options(doctor, option)
    if not slots:
        client.send_text(
            phone,
            "No open time slots on that date. Pick another date.\n\n"
            + _format_date_options(
                doctor, clinic, session.context.get("date_options") or [option]
            ),
        )
        session.state = WhatsAppSession.State.AWAITING_DATE
        session.save(update_fields=["state", "updated_at"])
        return
    session.state = WhatsAppSession.State.AWAITING_SLOT
    session.context = {
        **session.context,
        "doctor_id": doctor.id,
        "clinic_id": clinic.id,
        "token_date": option["date"],
        "date_label": option["label"],
        "timing": option["timing"],
        "start": option["start"],
        "slot_options": slots,
    }
    session.save(update_fields=["state", "context", "updated_at"])
    client.send_text(
        phone,
        f"{option['label']} @ {clinic.name}\n\n{_format_slot_options(slots)}",
    )


def _prompt_confirm(
    session: WhatsAppSession,
    client,
    phone: str,
    doctor: DoctorProfile,
    clinic: Clinic,
    *,
    date_label: str,
    token_date: str,
    slot_time: str,
    slot_label: str,
    timing: str,
) -> None:
    specs = ", ".join(s.name for s in doctor.specialities.filter(is_active=True)) or "—"
    session.state = WhatsAppSession.State.AWAITING_CONFIRM
    session.context = {
        "doctor_id": doctor.id,
        "clinic_id": clinic.id,
        "token_date": token_date,
        "slot_time": slot_time,
        "slot_label": slot_label,
        "start": slot_time,
        "timing": timing,
        "date_label": date_label,
        "clinic_name": clinic.name,
    }
    session.save(update_fields=["state", "context", "updated_at"])
    client.send_text(
        phone,
        "Confirm booking:\n"
        f"Doctor: Dr. {doctor.full_name}\n"
        f"Speciality: {specs}\n"
        f"Clinic: {clinic.name}\n"
        f"Date: {date_label}\n"
        f"Time: {slot_label} (Pakistan)\n"
        f"Session: {doctor.session_time} min\n\n"
        "Reply YES to confirm.\n"
        "Reply 0 to cancel.",
    )


def _resolve_speciality_choice(text: str, ordered: list[Speciality]) -> Speciality | None:
    idx = _parse_choice_index(text, len(ordered))
    if idx is not None:
        return ordered[idx]
    matches = _match_by_name(text, ordered, lambda s: s.name)
    if len(matches) == 1:
        return matches[0]
    return None


def _resolve_doctor_choice(text: str, ordered: list[DoctorProfile]) -> DoctorProfile | list[DoctorProfile] | None:
    idx = _parse_choice_index(text, len(ordered))
    if idx is not None:
        return ordered[idx]
    matches = _match_by_name(text, ordered, lambda d: d.full_name)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return matches
    return None


def handle_inbound_message(msg: dict, client) -> None:
    phone = _normalize_phone(str(msg.get("from", "")))
    if not phone:
        return

    message_id = str(msg.get("id", ""))
    session = _get_or_create_session(phone)
    if message_id and session.last_message_id == message_id:
        return
    if message_id:
        session.last_message_id = message_id
        session.save(update_fields=["last_message_id", "updated_at"])

    text = _message_text(msg)
    if not text:
        return

    patient = PatientProfile.objects.filter(phone=phone).first()
    profile_name = _clean_patient_name(str(msg.get("profile_name") or ""))

    # Refresh empty/placeholder names from WhatsApp profile when available
    if patient and profile_name:
        current = _clean_patient_name(patient.name)
        if not current or current == phone:
            patient.name = profile_name
            patient.save(update_fields=["name", "updated_at"])

    if not patient:
        if session.state == WhatsAppSession.State.AWAITING_NAME:
            name = _clean_patient_name(text)
            if not name:
                client.send_text(phone, "Please send your full name (at least 2 characters).")
                return
            PatientProfile.objects.create(phone=phone, name=name)
            _reset_to_menu(session)
            client.send_text(
                phone,
                f"Thanks {name}! Your Telemed profile is ready.\n\n{MENU_TEXT}",
            )
            return

        # Prefer WhatsApp profile name linked to this number
        if profile_name:
            PatientProfile.objects.create(phone=phone, name=profile_name)
            _reset_to_menu(session)
            client.send_text(
                phone,
                f"Welcome {profile_name}! Your Telemed profile is ready.\n\n{MENU_TEXT}",
            )
            return

        session.state = WhatsAppSession.State.AWAITING_NAME
        session.save(update_fields=["state", "updated_at"])
        client.send_text(
            phone,
            "Welcome to Telemed! We don't have your profile yet.\n"
            "Please reply with your full name to create an account.",
        )
        return

    choice = text.strip().lower()

    if session.state == WhatsAppSession.State.AWAITING_SPECIALITY:
        if choice in ("0", "cancel", "menu"):
            _reset_to_menu(session)
            client.send_text(phone, MENU_TEXT)
            return

        ids = session.context.get("speciality_ids") or []
        specialities = list(Speciality.objects.filter(id__in=ids, is_active=True))
        by_id = {s.id: s for s in specialities}
        ordered = [by_id[i] for i in ids if i in by_id]

        doctor_matches = _match_by_name(text, _active_doctors_all(), lambda d: d.full_name)
        if doctor_matches and _parse_choice_index(text, len(ordered)) is None:
            speciality_match = _resolve_speciality_choice(text, ordered)
            if speciality_match is None:
                if len(doctor_matches) == 1:
                    _prompt_clinic_selection(session, client, phone, doctor_matches[0])
                    return
                client.send_text(
                    phone,
                    "Multiple doctors matched:\n\n" + _format_doctors(doctor_matches[:10]),
                )
                session.state = WhatsAppSession.State.AWAITING_DOCTOR
                session.context = {"doctor_ids": [d.id for d in doctor_matches[:10]]}
                session.save(update_fields=["state", "context", "updated_at"])
                return

        speciality = _resolve_speciality_choice(text, ordered)
        if speciality is None:
            name_hits = _match_by_name(text, ordered, lambda s: s.name)
            if len(name_hits) > 1:
                client.send_text(
                    phone,
                    "Multiple specialities matched. Pick a number:\n\n"
                    + _format_specialities(name_hits),
                )
                session.context = {"speciality_ids": [s.id for s in name_hits]}
                session.save(update_fields=["context", "updated_at"])
                return
            client.send_text(
                phone,
                "Could not find that speciality or doctor.\n\n" + _format_specialities(ordered),
            )
            return

        doctors = _active_doctors_for_speciality(speciality.id)
        _offer_doctors(session, client, phone, speciality, doctors)
        return

    if session.state == WhatsAppSession.State.AWAITING_DOCTOR:
        if choice in ("0", "cancel", "menu"):
            _reset_to_menu(session)
            client.send_text(phone, MENU_TEXT)
            return
        ids = session.context.get("doctor_ids") or []
        doctors = list(
            DoctorProfile.objects.filter(id__in=ids, is_active=True).prefetch_related(
                "specialities"
            )
        )
        by_id = {d.id: d for d in doctors}
        ordered = [by_id[i] for i in ids if i in by_id]
        resolved = _resolve_doctor_choice(text, ordered)
        if resolved is None:
            client.send_text(phone, "Could not find that doctor.\n\n" + _format_doctors(ordered))
            return
        if isinstance(resolved, list):
            client.send_text(
                phone,
                "Multiple doctors matched. Pick a number or fuller name:\n\n"
                + _format_doctors(resolved),
            )
            session.context = {**session.context, "doctor_ids": [d.id for d in resolved]}
            session.save(update_fields=["context", "updated_at"])
            return
        _prompt_clinic_selection(session, client, phone, resolved)
        return

    if session.state == WhatsAppSession.State.AWAITING_CLINIC:
        if choice in ("0", "cancel", "menu"):
            _reset_to_menu(session)
            client.send_text(phone, MENU_TEXT)
            return
        doctor_id = session.context.get("doctor_id")
        clinic_ids = session.context.get("clinic_ids") or []
        doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
        clinics = list(Clinic.objects.filter(id__in=clinic_ids, is_active=True))
        by_id = {c.id: c for c in clinics}
        ordered = [by_id[i] for i in clinic_ids if i in by_id]
        if not doctor or not ordered:
            _reset_to_menu(session)
            client.send_text(phone, "Session expired. Please book again.\n\n" + MENU_TEXT)
            return
        idx = _parse_choice_index(text, len(ordered))
        if idx is None:
            client.send_text(phone, "Invalid choice.\n\n" + _format_clinics(ordered))
            return
        _prompt_date_selection(session, client, phone, doctor, ordered[idx])
        return

    if session.state == WhatsAppSession.State.AWAITING_DATE:
        if choice in ("0", "cancel", "menu"):
            _reset_to_menu(session)
            client.send_text(phone, MENU_TEXT)
            return
        options = session.context.get("date_options") or []
        doctor_id = session.context.get("doctor_id")
        clinic_id = session.context.get("clinic_id")
        doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
        clinic = Clinic.objects.filter(id=clinic_id, is_active=True).first()
        if not doctor or not clinic or not options:
            _reset_to_menu(session)
            client.send_text(phone, "Session expired. Please book again.\n\n" + MENU_TEXT)
            return
        idx = _parse_choice_index(text, len(options))
        if idx is None:
            client.send_text(
                phone,
                "Invalid choice.\n\n" + _format_date_options(doctor, clinic, options),
            )
            return
        _prompt_slot_selection(session, client, phone, doctor, clinic, options[idx])
        return

    if session.state == WhatsAppSession.State.AWAITING_SLOT:
        if choice in ("0", "cancel", "menu"):
            _reset_to_menu(session)
            client.send_text(phone, MENU_TEXT)
            return
        slots = session.context.get("slot_options") or []
        doctor_id = session.context.get("doctor_id")
        clinic_id = session.context.get("clinic_id")
        doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
        clinic = Clinic.objects.filter(id=clinic_id, is_active=True).first()
        if not doctor or not clinic or not slots:
            _reset_to_menu(session)
            client.send_text(phone, "Session expired. Please book again.\n\n" + MENU_TEXT)
            return
        idx = _parse_choice_index(text, len(slots))
        if idx is None:
            client.send_text(phone, "Invalid choice.\n\n" + _format_slot_options(slots))
            return
        picked = slots[idx]
        _prompt_confirm(
            session,
            client,
            phone,
            doctor,
            clinic,
            date_label=session.context.get("date_label", ""),
            token_date=session.context.get("token_date", ""),
            slot_time=picked["time"],
            slot_label=picked["label"],
            timing=session.context.get("timing", ""),
        )
        return

    if session.state == WhatsAppSession.State.AWAITING_CONFIRM:
        if choice in ("0", "cancel", "menu", "no", "n"):
            _reset_to_menu(session)
            client.send_text(phone, MENU_TEXT)
            return
        if choice not in ("1", "yes", "y", "confirm", "ok", "book"):
            doctor_id = session.context.get("doctor_id")
            clinic_id = session.context.get("clinic_id")
            doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
            clinic = Clinic.objects.filter(id=clinic_id, is_active=True).first()
            if doctor and clinic and session.context.get("slot_time"):
                _prompt_confirm(
                    session,
                    client,
                    phone,
                    doctor,
                    clinic,
                    date_label=session.context.get("date_label", ""),
                    token_date=session.context.get("token_date", ""),
                    slot_time=session.context["slot_time"],
                    slot_label=session.context.get("slot_label", ""),
                    timing=session.context.get("timing", ""),
                )
            else:
                _reset_to_menu(session)
                client.send_text(phone, "Session expired. Please book again.\n\n" + MENU_TEXT)
            return

        doctor_id = session.context.get("doctor_id")
        clinic_id = session.context.get("clinic_id")
        token_date_raw = session.context.get("token_date")
        slot_raw = session.context.get("slot_time")
        doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
        clinic = Clinic.objects.filter(id=clinic_id, is_active=True).first()
        if not doctor or not clinic or not token_date_raw or not slot_raw:
            _reset_to_menu(session)
            client.send_text(phone, "Doctor unavailable.\n\n" + MENU_TEXT)
            return

        token_date = date.fromisoformat(token_date_raw)
        slot_parts = [int(x) for x in slot_raw.split(":")[:3]]
        slot_time = time(*slot_parts)

        try:
            appt = book_token(
                patient,
                doctor,
                token_date,
                slot_time,
                slot_time=slot_time,
                clinic=clinic,
                notes="Booked via WhatsApp",
            )
        except ValueError as exc:
            _reset_to_menu(session)
            client.send_text(phone, f"{exc}\n\n{MENU_TEXT}")
            return
        except Exception:
            logger.exception("Booking failed for %s / doctor %s", phone, doctor.id)
            _reset_to_menu(session)
            client.send_text(phone, "Booking failed. Please try again.\n\n" + MENU_TEXT)
            return

        when = appt.token_date.strftime("%d %b %Y")
        slot_label = session.context.get("slot_label") or format_clock(slot_time)
        _reset_to_menu(session)
        client.send_text(
            phone,
            "Booked!\n"
            f"Doctor: Dr. {doctor.full_name}\n"
            f"Clinic: {clinic.name}\n"
            f"Date: {when}\n"
            f"Time: {slot_label} (Pakistan)\n"
            f"Your token: {appt.token_code}\n\n"
            "Show this token at the clinic.\n\n"
            f"{MENU_TEXT}",
        )
        return

    if session.state == WhatsAppSession.State.AWAITING_OTP and choice not in (
        "1",
        "2",
        "3",
        "otp",
        "login",
        "book",
        "appointments",
        "appointment",
        "menu",
    ):
        cached = cache.get(f"otp:{phone}")
        if cached and text.strip() == str(cached):
            patient.is_verified = True
            patient.save(update_fields=["is_verified", "updated_at"])
            cache.delete(f"otp:{phone}")
            _reset_to_menu(session)
            client.send_text(phone, "Login successful. You are verified.\n\n" + MENU_TEXT)
        else:
            client.send_text(phone, "Invalid or expired OTP. Reply 1 to request a new OTP.")
            _reset_to_menu(session)
        return

    if choice in ("1", "otp", "login"):
        otp = _generate_otp()
        cache.set(f"otp:{phone}", otp, timeout=300)
        session.state = WhatsAppSession.State.AWAITING_OTP
        session.context = {}
        session.save(update_fields=["state", "context", "updated_at"])
        client.send_text(
            phone,
            f"Your Telemed login OTP is: {otp}\nIt expires in 5 minutes.\nReply with the OTP to verify.",
        )
        return

    if choice in ("2", "book"):
        _start_booking(session, client, phone)
        return

    if choice in ("3", "appointments", "appointment"):
        client.send_text(phone, _format_appointments(patient))
        _reset_to_menu(session)
        return

    _reset_to_menu(session)
    client.send_text(phone, f"Hi {patient.name}!\n\n{MENU_TEXT}")
