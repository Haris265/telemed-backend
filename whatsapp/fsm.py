import logging
import random
import re
import string
from datetime import date, time
from decimal import Decimal

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.utils import timezone

from appointments.models import Appointment
from appointments.services import (
    book_token,
    format_clock,
    generate_slots_for_windows,
    pakistan_now,
    pakistan_today,
    upcoming_available_dates,
)
from appointments.slip_ocr import verify_payment_slip
from catalog.models import Clinic, DoctorAvailability, DoctorProfile, Speciality
from patients.models import PatientProfile

from .models import WhatsAppSession

logger = logging.getLogger(__name__)

MENU_TEXT = (
    "Welcome to PatientCare.\n\n"
    "Reply with:\n"
    "1. Book an appointment\n"
    "2. View my appointments\n"
    "0. Ask a question / mazeed maloomat\n\n"
    "Reply menu anytime to go home."
)

CANCEL_CHOICES = ("cancel", "menu", "9")
BANK_CHOICES = ("1", "bank", "transfer", "bank transfer", "bank_transfer")
CASH_CHOICES = ("2", "cash", "clinic", "cash at clinic", "cash_at_clinic")
MARKETPLACE_STATES = {
    WhatsAppSession.State.AWAITING_SPECIALITY,
    WhatsAppSession.State.AWAITING_DOCTOR,
    WhatsAppSession.State.AWAITING_CLINIC_DOCTOR,
    WhatsAppSession.State.AWAITING_BOOKING_MODE,
}


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
    # Caption on image can carry text commands (e.g. cash / cancel)
    if msg.get("type") == "image":
        return ((msg.get("image") or {}).get("caption") or "").strip()
    return ""


def _message_image_id(msg: dict) -> str:
    if msg.get("type") != "image":
        return ""
    return str((msg.get("image") or {}).get("id") or "").strip()


def _message_audio_id(msg: dict) -> str:
    if msg.get("type") not in ("audio", "voice"):
        return ""
    payload = msg.get("audio") or msg.get("voice") or {}
    return str(payload.get("id") or "").strip()


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


def _bound_doctor(session: WhatsAppSession) -> DoctorProfile | None:
    if not isinstance(session.context, dict):
        return None
    bound_id = session.context.get("bound_doctor_id")
    if not bound_id:
        return None
    return DoctorProfile.objects.filter(id=bound_id, is_active=True).first()


def _menu_text(session: WhatsAppSession) -> str:
    doctor = _bound_doctor(session)
    if doctor:
        return (
            f"You're messaging Dr. {doctor.full_name}'s WhatsApp.\n\n"
            "Reply with:\n"
            "1. Book an appointment\n"
            "2. View my appointments\n"
            "0. Ask a question / mazeed maloomat\n\n"
            "Reply menu anytime to go home."
        )
    return MENU_TEXT


def _format_availability(doctor: DoctorProfile, clinic: Clinic | None = None) -> str:
    qs = DoctorAvailability.objects.filter(
        doctor=doctor,
        is_active=True,
        clinic__isnull=False,
        specific_date__isnull=True,
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
    lines.append("\nReply menu to cancel.")
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
    lines.append("\nReply menu to cancel.")
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
    lines.append("\nReply menu to cancel.")
    return "\n".join(lines)


def _format_specialities(items: list[Speciality]) -> str:
    lines = [
        "Select a speciality — reply with number OR name.",
        "Or type a doctor name (e.g. Ayesha Khan) to book directly.",
        "",
    ]
    for i, s in enumerate(items, start=1):
        lines.append(f"{i}. {s.name}")
    lines.append("\nReply menu to cancel.")
    return "\n".join(lines)


def _format_doctors(items: list[DoctorProfile]) -> str:
    lines = ["Select a doctor — reply with number OR name:"]
    for i, d in enumerate(items, start=1):
        lines.append(f"{i}. Dr. {d.full_name} ({d.session_time} min)")
    lines.append("\nReply menu to cancel.")
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
    bound = session.context.get("bound_doctor_id") if isinstance(session.context, dict) else None
    session.state = WhatsAppSession.State.MENU
    session.context = {"bound_doctor_id": bound} if bound else {}
    session.save(update_fields=["state", "context", "updated_at"])


def _ctx(session: WhatsAppSession, **kwargs) -> dict:
    """Build session context while preserving per-number bound doctor."""
    bound = None
    if isinstance(session.context, dict):
        bound = session.context.get("bound_doctor_id")
    data = dict(kwargs)
    if bound is not None:
        data["bound_doctor_id"] = bound
    return data


def _start_booking(session: WhatsAppSession, client, phone: str) -> None:
    # Dedicated doctor WhatsApp: skip specialty/doctor pickers.
    bound = _bound_doctor(session)
    if session.context.get("bound_doctor_id") and not bound:
        client.send_text(
            phone,
            "This doctor's WhatsApp booking is unavailable right now.\n\n"
            + _menu_text(session),
        )
        _reset_to_menu(session)
        return
    if bound:
        client.send_text(phone, f"Booking with Dr. {bound.full_name}.")
        _prompt_clinic_selection(session, client, phone, bound)
        return

    # Marketplace: speciality → doctor → clinic → date → slot
    specialities = _active_specialities()
    if not specialities:
        client.send_text(phone, "No specialities available right now. Please try later.")
        _reset_to_menu(session)
        return
    session.state = WhatsAppSession.State.AWAITING_SPECIALITY
    session.context = _ctx(session, speciality_ids=[s.id for s in specialities])
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
            f"No doctors available for {speciality.name} right now.\n\n{_menu_text(session)}",
        )
        _reset_to_menu(session)
        return
    session.state = WhatsAppSession.State.AWAITING_DOCTOR
    session.context = _ctx(
        session,
        speciality_id=speciality.id,
        doctor_ids=[d.id for d in doctors],
    )
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
            f"Dr. {doctor.full_name} has no clinic schedule yet.\n\n{_menu_text(session)}",
        )
        _reset_to_menu(session)
        return
    if len(clinics) == 1:
        _prompt_date_selection(session, client, phone, doctor, clinics[0])
        return
    session.state = WhatsAppSession.State.AWAITING_CLINIC
    session.context = _ctx(
        session,
        doctor_id=doctor.id,
        clinic_ids=[c.id for c in clinics],
    )
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
            f"Dr. {doctor.full_name} has no upcoming dates at {clinic.name}.\n\n"
            + _menu_text(session),
        )
        _reset_to_menu(session)
        return
    session.state = WhatsAppSession.State.AWAITING_DATE
    session.context = _ctx(
        session,
        doctor_id=doctor.id,
        clinic_id=clinic.id,
        date_options=options,
    )
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
    session.context = _ctx(
        session,
        doctor_id=doctor.id,
        clinic_id=clinic.id,
        token_date=option["date"],
        date_label=option["label"],
        timing=option["timing"],
        start=option["start"],
        slot_options=slots,
        date_options=session.context.get("date_options") or [],
    )
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
    session.context = _ctx(
        session,
        doctor_id=doctor.id,
        clinic_id=clinic.id,
        token_date=token_date,
        slot_time=slot_time,
        slot_label=slot_label,
        start=slot_time,
        timing=timing,
        date_label=date_label,
        clinic_name=clinic.name,
    )
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
        "Reply menu to cancel.",
    )


def _load_booking_context(
    session: WhatsAppSession,
) -> tuple[DoctorProfile | None, Clinic | None, date | None, time | None]:
    doctor_id = session.context.get("doctor_id")
    clinic_id = session.context.get("clinic_id")
    token_date_raw = session.context.get("token_date")
    slot_raw = session.context.get("slot_time")
    doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
    clinic = Clinic.objects.filter(id=clinic_id, is_active=True).first()
    token_date = None
    slot_time = None
    if token_date_raw:
        try:
            token_date = date.fromisoformat(str(token_date_raw))
        except ValueError:
            token_date = None
    if slot_raw:
        try:
            slot_parts = [int(x) for x in str(slot_raw).split(":")[:3]]
            slot_time = time(*slot_parts)
        except (TypeError, ValueError):
            slot_time = None
    return doctor, clinic, token_date, slot_time


def _prompt_payment_method(session: WhatsAppSession, client, phone: str) -> None:
    doctor, clinic, token_date, slot_time = _load_booking_context(session)
    if not doctor or not clinic or not token_date or not slot_time:
        _reset_to_menu(session)
        client.send_text(phone, "Session expired. Please book again.\n\n" + _menu_text(session))
        return
    fee = doctor.consultation_fee or Decimal("0")
    session.state = WhatsAppSession.State.AWAITING_PAYMENT_METHOD
    session.save(update_fields=["state", "updated_at"])
    client.send_text(
        phone,
        "Choose payment method:\n"
        f"Fee: Rs {fee}\n\n"
        "1. Bank transfer (send payment slip on WhatsApp)\n"
        "2. Cash at clinic\n\n"
        "Reply 1 or 2.\n"
        "Reply menu to cancel.",
    )


def _format_bank_accounts(doctor: DoctorProfile) -> str:
    accounts = list(
        doctor.bank_accounts.filter(is_active=True).order_by("-is_primary", "-created_at")
    )
    if not accounts:
        return ""
    lines: list[str] = []
    for i, acc in enumerate(accounts, start=1):
        primary = " (primary)" if acc.is_primary else ""
        block = (
            f"{i}. {acc.bank_name}{primary}\n"
            f"   Title: {acc.account_title}\n"
            f"   Account: {acc.account_number}"
        )
        if acc.iban:
            block += f"\n   IBAN: {acc.iban}"
        lines.append(block)
    return "\n".join(lines)


def _prompt_bank_transfer(
    session: WhatsAppSession, client, phone: str, doctor: DoctorProfile
) -> None:
    fee = doctor.consultation_fee or Decimal("0")
    if fee <= 0:
        client.send_text(
            phone,
            "This doctor has not set a consultation fee yet.\n"
            "Please choose Cash at clinic (reply 2) or reply menu to cancel.",
        )
        return
    banks = _format_bank_accounts(doctor)
    if not banks:
        client.send_text(
            phone,
            "This doctor has no bank account on profile yet.\n"
            "Please choose Cash at clinic (reply 2) or reply menu to cancel.",
        )
        return
    session.state = WhatsAppSession.State.AWAITING_PAYMENT_SLIP
    session.save(update_fields=["state", "updated_at"])
    client.send_text(
        phone,
        "Bank transfer payment:\n"
        f"Amount to transfer: Rs {fee}\n\n"
        f"{banks}\n\n"
        "Transfer the exact amount, then send a clear photo of the payment slip here.\n"
        "Reply 2 for Cash at clinic instead.\n"
        "Reply menu to cancel.",
    )


def _complete_booking_message(
    *,
    doctor: DoctorProfile,
    clinic: Clinic,
    appt: Appointment,
    slot_label: str,
    payment_note: str,
) -> str:
    when = appt.token_date.strftime("%d %b %Y")
    return (
        "Booked!\n"
        f"Doctor: Dr. {doctor.full_name}\n"
        f"Clinic: {clinic.name}\n"
        f"Date: {when}\n"
        f"Time: {slot_label} (Pakistan)\n"
        f"Your token: {appt.token_code}\n"
        f"{payment_note}\n\n"
        "Show this token at the clinic."
    )


def _book_cash_appointment(
    session: WhatsAppSession,
    client,
    phone: str,
    patient: PatientProfile,
) -> None:
    doctor, clinic, token_date, slot_time = _load_booking_context(session)
    if not doctor or not clinic or not token_date or not slot_time:
        _reset_to_menu(session)
        client.send_text(phone, "Session expired. Please book again.\n\n" + _menu_text(session))
        return
    bound = _bound_doctor(session)
    if bound and doctor.id != bound.id:
        _reset_to_menu(session)
        client.send_text(
            phone,
            f"This WhatsApp only books with Dr. {bound.full_name}.\n\n"
            + _menu_text(session),
        )
        return
    fee = doctor.consultation_fee or Decimal("0")
    try:
        appt = book_token(
            patient,
            doctor,
            token_date,
            slot_time,
            slot_time=slot_time,
            clinic=clinic,
            notes="Booked via WhatsApp",
            payment_method=Appointment.PaymentMethod.CASH_AT_CLINIC,
            payment_status=Appointment.PaymentStatus.PENDING,
            payment_amount_expected=fee if fee > 0 else None,
            payment_ocr_status=Appointment.PaymentOcrStatus.SKIPPED,
        )
    except ValueError as exc:
        _reset_to_menu(session)
        client.send_text(phone, f"{exc}\n\n{_menu_text(session)}")
        return
    except Exception:
        logger.exception("Cash booking failed for %s / doctor %s", phone, doctor.id)
        _reset_to_menu(session)
        client.send_text(
            phone, "Booking failed. Please try again.\n\n" + _menu_text(session)
        )
        return

    slot_label = session.context.get("slot_label") or format_clock(slot_time)
    _reset_to_menu(session)
    client.send_text(
        phone,
        _complete_booking_message(
            doctor=doctor,
            clinic=clinic,
            appt=appt,
            slot_label=slot_label,
            payment_note="Payment: Cash at clinic (pending)",
        )
        + f"\n\n{_menu_text(session)}",
    )


def _book_bank_after_ocr(
    session: WhatsAppSession,
    client,
    phone: str,
    patient: PatientProfile,
    *,
    image_bytes: bytes,
    mime_type: str,
) -> None:
    doctor, clinic, token_date, slot_time = _load_booking_context(session)
    if not doctor or not clinic or not token_date or not slot_time:
        _reset_to_menu(session)
        client.send_text(phone, "Session expired. Please book again.\n\n" + _menu_text(session))
        return
    bound = _bound_doctor(session)
    if bound and doctor.id != bound.id:
        _reset_to_menu(session)
        client.send_text(
            phone,
            f"This WhatsApp only books with Dr. {bound.full_name}.\n\n"
            + _menu_text(session),
        )
        return

    fee = doctor.consultation_fee or Decimal("0")
    if fee <= 0:
        client.send_text(
            phone,
            "Consultation fee is not set. Reply 2 for Cash at clinic, or menu to cancel.",
        )
        return

    client.send_text(phone, "Checking your payment slip…")
    result = verify_payment_slip(
        image_bytes=image_bytes,
        mime_type=mime_type or "image/jpeg",
        expected_amount=fee,
        expected_date=token_date,
    )
    if not result.ok:
        client.send_text(
            phone,
            "Payment slip could not be verified.\n"
            f"{result.error or 'Please send a clearer slip photo.'}\n\n"
            "Send the slip image again, reply 2 for Cash at clinic, or menu to cancel.",
        )
        return

    try:
        appt = book_token(
            patient,
            doctor,
            token_date,
            slot_time,
            slot_time=slot_time,
            clinic=clinic,
            notes="Booked via WhatsApp",
            payment_method=Appointment.PaymentMethod.BANK_TRANSFER,
            payment_status=Appointment.PaymentStatus.PAID,
            payment_amount_expected=fee,
            payment_amount_received=result.amount,
            payment_reference=result.reference,
            payment_ocr_raw=result.raw,
            payment_ocr_status=Appointment.PaymentOcrStatus.PASSED,
            payment_verified_at=timezone.now(),
        )
    except ValueError as exc:
        _reset_to_menu(session)
        client.send_text(phone, f"{exc}\n\n{_menu_text(session)}")
        return
    except Exception:
        logger.exception("Bank booking failed for %s / doctor %s", phone, doctor.id)
        _reset_to_menu(session)
        client.send_text(
            phone, "Booking failed. Please try again.\n\n" + _menu_text(session)
        )
        return

    ext = ".jpg"
    if "png" in (mime_type or "").lower():
        ext = ".png"
    elif "webp" in (mime_type or "").lower():
        ext = ".webp"
    filename = f"slip_{appt.id}_{result.reference[:32] or 'payment'}{ext}"
    appt.payment_slip.save(filename, ContentFile(image_bytes), save=True)

    slot_label = session.context.get("slot_label") or format_clock(slot_time)
    _reset_to_menu(session)
    client.send_text(
        phone,
        _complete_booking_message(
            doctor=doctor,
            clinic=clinic,
            appt=appt,
            slot_label=slot_label,
            payment_note=(
                f"Payment: Bank transfer confirmed (ref {result.reference})"
            ),
        )
        + f"\n\n{_menu_text(session)}",
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


def _redirect_bound_away_from_marketplace(
    session: WhatsAppSession, client, phone: str
) -> bool:
    """Linked/testing Meta number must never continue marketplace specialty flows."""
    bound = _bound_doctor(session)
    if not bound:
        return False
    if session.state not in MARKETPLACE_STATES:
        return False
    client.send_text(
        phone,
        f"You're messaging Dr. {bound.full_name}'s WhatsApp. "
        "Booking stays with this doctor.\n",
    )
    _start_booking(session, client, phone)
    return True


def handle_inbound_message(msg: dict, client, doctor: DoctorProfile | None = None) -> None:
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

    # Meta Embedded Signup or testing/manual connect: bind FSM to this doctor only.
    # Bind only when webhook resolved a dedicated doctor number.
    # Platform / shared Meta number passes doctor=None → clear any stale bind
    # left over from testing/manual connect on the same credentials.
    if doctor is not None:
        ctx = dict(session.context or {})
        if ctx.get("bound_doctor_id") != doctor.id:
            ctx["bound_doctor_id"] = doctor.id
            session.context = ctx
            session.save(update_fields=["context", "updated_at"])
    elif isinstance(session.context, dict) and session.context.get("bound_doctor_id"):
        ctx = dict(session.context)
        ctx.pop("bound_doctor_id", None)
        session.context = ctx
        session.save(update_fields=["context", "updated_at"])

    text = _message_text(msg)
    image_id = _message_image_id(msg)
    audio_id = _message_audio_id(msg)
    awaiting_slip = session.state == WhatsAppSession.State.AWAITING_PAYMENT_SLIP
    awaiting_faq = session.state == WhatsAppSession.State.AWAITING_FAQ_QUESTION
    if not text and not (awaiting_slip and image_id) and not (awaiting_faq and audio_id):
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
        if (awaiting_slip and image_id) or (awaiting_faq and audio_id):
            client.send_text(
                phone,
                "Please create your PatientCare profile first (send your full name).",
            )
            return
        if session.state == WhatsAppSession.State.AWAITING_NAME:
            name = _clean_patient_name(text)
            if not name:
                client.send_text(phone, "Please send your full name (at least 2 characters).")
                return
            PatientProfile.objects.create(phone=phone, name=name)
            _reset_to_menu(session)
            client.send_text(
                phone,
                f"Thanks {name}! Your PatientCare profile is ready.\n\n{_menu_text(session)}",
            )
            return

        # Prefer WhatsApp profile name linked to this number
        if profile_name:
            PatientProfile.objects.create(phone=phone, name=profile_name)
            _reset_to_menu(session)
            client.send_text(
                phone,
                f"Welcome {profile_name}! Your PatientCare profile is ready.\n\n"
                + _menu_text(session),
            )
            return

        session.state = WhatsAppSession.State.AWAITING_NAME
        session.save(update_fields=["state", "updated_at"])
        client.send_text(
            phone,
            "Welcome to PatientCare! We don't have your profile yet.\n"
            "Please reply with your full name to create an account.",
        )
        return

    choice = text.strip().lower()

    if _redirect_bound_away_from_marketplace(session, client, phone):
        return

    # Stale mid-flow from removed clinic/mode menus → restart specialty booking.
    if session.state in (
        WhatsAppSession.State.AWAITING_BOOKING_MODE,
        WhatsAppSession.State.AWAITING_CLINIC_DOCTOR,
    ):
        _start_booking(session, client, phone)
        return

    if session.state == WhatsAppSession.State.AWAITING_SPECIALITY:
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
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
                session.context = _ctx(
                    session, doctor_ids=[d.id for d in doctor_matches[:10]]
                )
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
                session.context = _ctx(
                    session, speciality_ids=[s.id for s in name_hits]
                )
                session.save(update_fields=["context", "updated_at"])
                return
            client.send_text(
                phone,
                "Could not find that speciality or doctor.\n\n"
                + _format_specialities(ordered),
            )
            return

        doctors = _active_doctors_for_speciality(speciality.id)
        _offer_doctors(session, client, phone, speciality, doctors)
        return

    if session.state == WhatsAppSession.State.AWAITING_DOCTOR:
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
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
            prev_speciality = session.context.get("speciality_id")
            session.context = _ctx(
                session,
                doctor_ids=[d.id for d in resolved],
                **({"speciality_id": prev_speciality} if prev_speciality else {}),
            )
            session.save(update_fields=["context", "updated_at"])
            return
        _prompt_clinic_selection(session, client, phone, resolved)
        return

    if session.state == WhatsAppSession.State.AWAITING_CLINIC:
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
            return
        clinic_ids = session.context.get("clinic_ids") or []
        clinics = list(Clinic.objects.filter(id__in=clinic_ids, is_active=True))
        by_id = {c.id: c for c in clinics}
        ordered = [by_id[i] for i in clinic_ids if i in by_id]
        doctor_id = session.context.get("doctor_id")
        doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
        if not doctor or not ordered:
            _reset_to_menu(session)
            client.send_text(
                phone, "Session expired. Please book again.\n\n" + _menu_text(session)
            )
            return
        idx = _parse_choice_index(text, len(ordered))
        if idx is None:
            client.send_text(phone, "Invalid choice.\n\n" + _format_clinics(ordered))
            return
        _prompt_date_selection(session, client, phone, doctor, ordered[idx])
        return

    if session.state == WhatsAppSession.State.AWAITING_DATE:
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
            return
        options = session.context.get("date_options") or []
        doctor_id = session.context.get("doctor_id")
        clinic_id = session.context.get("clinic_id")
        doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
        clinic = Clinic.objects.filter(id=clinic_id, is_active=True).first()
        if not doctor or not clinic or not options:
            _reset_to_menu(session)
            client.send_text(
                phone, "Session expired. Please book again.\n\n" + _menu_text(session)
            )
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
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
            return
        slots = session.context.get("slot_options") or []
        doctor_id = session.context.get("doctor_id")
        clinic_id = session.context.get("clinic_id")
        doctor = DoctorProfile.objects.filter(id=doctor_id, is_active=True).first()
        clinic = Clinic.objects.filter(id=clinic_id, is_active=True).first()
        if not doctor or not clinic or not slots:
            _reset_to_menu(session)
            client.send_text(
                phone, "Session expired. Please book again.\n\n" + _menu_text(session)
            )
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
        if choice in (*CANCEL_CHOICES, "no", "n"):
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
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
                client.send_text(
                    phone,
                    "Session expired. Please book again.\n\n" + _menu_text(session),
                )
            return

        doctor, clinic, token_date, slot_time = _load_booking_context(session)
        if not doctor or not clinic or not token_date or not slot_time:
            _reset_to_menu(session)
            client.send_text(phone, "Doctor unavailable.\n\n" + _menu_text(session))
            return

        bound = _bound_doctor(session)
        if bound and doctor.id != bound.id:
            _reset_to_menu(session)
            client.send_text(
                phone,
                f"This WhatsApp only books with Dr. {bound.full_name}.\n\n"
                + _menu_text(session),
            )
            return

        _prompt_payment_method(session, client, phone)
        return

    if session.state == WhatsAppSession.State.AWAITING_PAYMENT_METHOD:
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
            return
        if choice in CASH_CHOICES:
            _book_cash_appointment(session, client, phone, patient)
            return
        if choice in BANK_CHOICES:
            doctor, _, _, _ = _load_booking_context(session)
            if not doctor:
                _reset_to_menu(session)
                client.send_text(
                    phone, "Session expired. Please book again.\n\n" + _menu_text(session)
                )
                return
            _prompt_bank_transfer(session, client, phone, doctor)
            return
        client.send_text(
            phone,
            "Reply 1 for Bank transfer, 2 for Cash at clinic, or menu to cancel.",
        )
        return

    if session.state == WhatsAppSession.State.AWAITING_PAYMENT_SLIP:
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
            return
        if choice in CASH_CHOICES:
            _book_cash_appointment(session, client, phone, patient)
            return
        if image_id:
            downloaded = None
            if hasattr(client, "download_media"):
                downloaded = client.download_media(image_id)
            if not downloaded:
                client.send_text(
                    phone,
                    "Could not download your slip image. Please send it again, "
                    "or reply 2 for Cash at clinic.",
                )
                return
            image_bytes, mime_type = downloaded
            _book_bank_after_ocr(
                session,
                client,
                phone,
                patient,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
            return
        client.send_text(
            phone,
            "Please send a photo of your payment slip, reply 2 for Cash at clinic, "
            "or menu to cancel.",
        )
        return

    if session.state == WhatsAppSession.State.AWAITING_FAQ_QUESTION:
        if choice in CANCEL_CHOICES:
            _reset_to_menu(session)
            client.send_text(phone, _menu_text(session))
            return
        from whatsapp.faq_bot import answer_faq

        bound = _bound_doctor(session)
        if audio_id and hasattr(client, "download_media"):
            client.send_text(phone, "Samajh raha hoon…")
            downloaded = client.download_media(audio_id)
            if not downloaded:
                client.send_text(
                    phone,
                    "Voice note download nahi hui. Dobara bhejein, ya text mein sawal likhein.\n"
                    "Reply menu to go home.",
                )
                return
            audio_bytes, mime_type = downloaded
            reply = answer_faq(
                question_text=text,
                audio_bytes=audio_bytes,
                audio_mime=mime_type or "audio/ogg",
                bound_doctor=bound,
            )
        elif text:
            client.send_text(phone, "Samajh raha hoon…")
            reply = answer_faq(question_text=text, bound_doctor=bound)
        else:
            client.send_text(
                phone,
                "Apna sawal text ya voice note mein bhejein.\nReply menu to go home.",
            )
            return
        client.send_text(phone, reply + "\n\n" + _menu_text(session))
        _reset_to_menu(session)
        return

    # OTP menu hidden for now; keep verify path if user already has pending OTP.
    if session.state == WhatsAppSession.State.AWAITING_OTP and choice not in (
        "1",
        "2",
        "0",
        "book",
        "appointments",
        "appointment",
        "menu",
        "cancel",
        "9",
    ):
        cached = cache.get(f"otp:{phone}")
        if cached and text.strip() == str(cached):
            patient.is_verified = True
            patient.save(update_fields=["is_verified", "updated_at"])
            cache.delete(f"otp:{phone}")
            _reset_to_menu(session)
            client.send_text(
                phone, "Login successful. You are verified.\n\n" + _menu_text(session)
            )
        else:
            client.send_text(
                phone,
                "Invalid or expired OTP. Reply menu for options.",
            )
            _reset_to_menu(session)
        return

    if choice in ("0", "faq", "help", "question", "maloomat"):
        session.state = WhatsAppSession.State.AWAITING_FAQ_QUESTION
        session.save(update_fields=["state", "updated_at"])
        client.send_text(
            phone,
            "Mazeed maloomat — apna sawal text ya voice note mein bhejein.\n"
            "Maslan: doctor kis shehar mein hain, speciality kya hai, "
            "kitne din pehle booking ho sakti hai.\n\n"
            "Reply menu to go home.",
        )
        return

    if choice in ("1", "book"):
        _start_booking(session, client, phone)
        return

    if choice in ("2", "appointments", "appointment"):
        client.send_text(phone, _format_appointments(patient))
        _reset_to_menu(session)
        return

    # Hidden OTP keywords (not shown on menu) for internal/testing only.
    if choice in ("otp", "login"):
        otp = _generate_otp()
        cache.set(f"otp:{phone}", otp, timeout=300)
        session.state = WhatsAppSession.State.AWAITING_OTP
        session.context = _ctx(session)
        session.save(update_fields=["state", "context", "updated_at"])
        client.send_text(
            phone,
            f"Your PatientCare login OTP is: {otp}\n"
            "It expires in 5 minutes.\n"
            "Reply with the OTP to verify.",
        )
        return

    _reset_to_menu(session)
    client.send_text(phone, f"Hi {patient.name}!\n\n{_menu_text(session)}")
