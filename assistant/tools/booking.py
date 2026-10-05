"""Two-phase booking tools and pending discard."""

from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field

from appointments.services import pakistan_now, pakistan_today
from patients.serializers import clean_name

from assistant.context import ClinicContext
from assistant.repo import ClinicCatalogRepo
from assistant.services import slots as slot_svc
from assistant.services.booking import book_cash_appointment
from assistant.services.patients import get_or_create_patient
from assistant.session_store import set_patient_name, set_pending


class NameArgs(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)


class PrepareBookingArgs(BaseModel):
    doctor_id: int = Field(..., gt=0)
    token_date: str = Field(..., description="YYYY-MM-DD")
    slot_time: str = Field(..., description="HH:MM:SS")


class EmptyArgs(BaseModel):
    pass


def build_booking_tools(ctx: ClinicContext, session: dict):
    from . import err, ok, wrap_tool

    repo = ClinicCatalogRepo(ctx.clinic)

    def set_patient_name_tool(name: str) -> str:
        cleaned = clean_name(name)
        if not cleaned:
            return err("invalid_argument", "Please provide a real name (not only digits).")
        set_patient_name(session, cleaned)
        return ok({"patient_name": cleaned})

    def prepare_booking(doctor_id: int, token_date: str, slot_time: str) -> str:
        doctor = repo.get_doctor(doctor_id)
        if doctor is None:
            return err("not_in_clinic", "That doctor is not available at this clinic.")
        if not doctor.is_active:
            return err("doctor_inactive", "That doctor is currently inactive.")
        try:
            day = date.fromisoformat(token_date)
        except ValueError:
            return err("invalid_argument", "token_date must be YYYY-MM-DD.")
        try:
            slot = slot_svc.parse_slot_time(slot_time)
        except Exception:
            return err("invalid_argument", "slot_time must be HH:MM:SS.")
        if day < pakistan_today():
            return err("past_slot", "That date is in the past.")
        open_times = slot_svc.open_times_for_date(doctor, ctx.clinic, day)
        open_keys = {t["time"] for t in open_times}
        key = slot.strftime("%H:%M:%S")
        if key not in open_keys:
            if day == pakistan_today() and slot <= pakistan_now().time():
                return err("past_slot", "That time has already passed today.")
            return err("slot_unavailable", "That time is not available.", hint="Pick another open slot.")
        pending = {
            "type": "booking",
            "doctor_id": doctor.id,
            "doctor_name": f"Dr. {doctor.full_name}",
            "token_date": day.isoformat(),
            "slot_time": key,
            "fee": str(doctor.consultation_fee),
            "prepared_at_turn": int(session.get("turn_no") or 0),
        }
        set_pending(session, pending)
        return ok(
            {
                "confirm_summary": {
                    "doctor": pending["doctor_name"],
                    "clinic": ctx.clinic.name,
                    "date": day.isoformat(),
                    "time": slot_svc.label_slot(slot),
                    "fee": pending["fee"],
                    "payment": "pay cash at clinic",
                }
            }
        )

    def confirm_booking() -> str:
        pending = session.get("pending")
        if not pending or pending.get("type") != "booking":
            return err("no_pending_action", "There is no booking waiting for confirmation.")
        if int(pending.get("prepared_at_turn") or 0) >= int(session.get("turn_no") or 0):
            return err(
                "pending_not_confirmed",
                "Wait for the patient to confirm in a new message before booking.",
            )
        name = clean_name(session.get("patient_name") or "")
        if not name:
            return err("needs_name", "Ask for the patient's name before confirming.")
        doctor = repo.get_doctor(int(pending["doctor_id"]))
        if doctor is None or not doctor.is_active:
            set_pending(session, None)
            return err("not_in_clinic", "That doctor is no longer available at this clinic.")
        day = date.fromisoformat(pending["token_date"])
        slot = slot_svc.parse_slot_time(pending["slot_time"])
        open_times = slot_svc.open_times_for_date(doctor, ctx.clinic, day)
        if slot.strftime("%H:%M:%S") not in {t["time"] for t in open_times}:
            set_pending(session, None)
            return err("slot_taken", "That slot is no longer available. Offer alternatives.")
        patient = get_or_create_patient(phone=ctx.phone, name=name)
        try:
            appt = book_cash_appointment(
                patient=patient,
                doctor=doctor,
                clinic=ctx.clinic,
                token_date=day,
                slot_time=slot,
            )
        except ValueError as exc:
            msg = str(exc)
            code = "duplicate_booking" if "already have Token" in msg else "slot_taken"
            return err(code, msg)
        set_pending(session, None)
        return ok(
            {
                "token_code": appt.token_code,
                "doctor": f"Dr. {doctor.full_name}",
                "clinic": ctx.clinic.name,
                "date_label": day.strftime("%d %b %Y"),
                "time_label": slot_svc.label_slot(slot),
                "fee": str(doctor.consultation_fee),
            }
        )

    def discard_pending() -> str:
        set_pending(session, None)
        return ok({"discarded": True})

    return [
        wrap_tool(
            "set_patient_name",
            "Store the patient's name in the session before booking.",
            NameArgs,
            lambda name: set_patient_name_tool(name),
        ),
        wrap_tool(
            "prepare_booking",
            "Validate and stage a cash booking for patient confirmation.",
            PrepareBookingArgs,
            lambda doctor_id, token_date, slot_time: prepare_booking(
                doctor_id, token_date, slot_time
            ),
        ),
        wrap_tool(
            "confirm_booking",
            "Confirm the pending booking after the patient explicitly says yes.",
            EmptyArgs,
            lambda: confirm_booking(),
        ),
        wrap_tool(
            "discard_pending",
            "Clear any pending booking or cancellation when the patient changes their mind.",
            EmptyArgs,
            lambda: discard_pending(),
        ),
    ]
