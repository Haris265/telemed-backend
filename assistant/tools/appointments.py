"""List appointments and two-phase cancellation tools."""

from __future__ import annotations

from pydantic import BaseModel, Field

from appointments.models import Appointment
from appointments.services import pakistan_today

from assistant.context import ClinicContext
from assistant.services.cancellation import (
    CancellationNotAllowed,
    cancel_flags,
    cancel_for_patient,
)
from assistant.services.patients import find_patient_by_phone
from assistant.services import slots as slot_svc
from assistant.session_store import resolve_ref, set_pending, set_refs


class EmptyArgs(BaseModel):
    pass


class CancelPrepareArgs(BaseModel):
    appointment_ref: str = Field(
        ...,
        description="Token code (e.g. AH-003) or 1-based number from the last listing.",
    )


def build_appointment_tools(ctx: ClinicContext, session: dict):
    from . import err, ok, wrap_tool

    def _upcoming_qs(patient):
        return (
            Appointment.objects.filter(
                patient=patient,
                clinic_id=ctx.clinic.id,
                status=Appointment.Status.UPCOMING,
                token_date__gte=pakistan_today(),
            )
            .select_related("doctor", "clinic")
            .order_by("token_date", "token_number")[:5]
        )

    def _row(appt: Appointment, n: int) -> dict:
        flags = cancel_flags(appt)
        return {
            "n": n,
            "appointment_id": appt.id,
            "token_code": appt.token_code,
            "doctor": f"Dr. {appt.doctor.full_name}",
            "date": appt.token_date.isoformat(),
            "date_label": appt.token_date.strftime("%d %b %Y"),
            "time_label": slot_svc.label_datetime(appt.scheduled_at),
            "status": appt.status,
            "can_cancel": flags["can_cancel"],
            "cancel_until": flags["cancel_until"],
        }

    def list_my_appointments() -> str:
        patient = find_patient_by_phone(ctx.phone)
        if patient is None:
            set_refs(session, [])
            return ok({"appointments": []})
        rows = []
        refs = []
        for i, appt in enumerate(_upcoming_qs(patient), start=1):
            rows.append(_row(appt, i))
            refs.append(
                {
                    "n": i,
                    "kind": "appointment",
                    "id": appt.id,
                    "label": appt.token_code,
                    "token_code": appt.token_code,
                }
            )
        set_refs(session, refs)
        return ok({"appointments": rows})

    def _short_list(patient) -> list[dict]:
        return [_row(a, i) for i, a in enumerate(_upcoming_qs(patient), start=1)]

    def _resolve_appointment(patient, appointment_ref: str):
        ref = (appointment_ref or "").strip()
        if not ref:
            return None, "ambiguous_appointment"
        # Numeric listing index
        if ref.isdigit():
            found = resolve_ref(session, int(ref))
            if found and found.get("kind") == "appointment":
                appt = (
                    Appointment.objects.filter(
                        pk=found["id"],
                        patient=patient,
                        clinic_id=ctx.clinic.id,
                        status=Appointment.Status.UPCOMING,
                    )
                    .select_related("doctor", "clinic")
                    .first()
                )
                return appt, None
            # Fall through to token/number among upcoming
            appts = list(_upcoming_qs(patient))
            idx = int(ref)
            if 1 <= idx <= len(appts):
                return appts[idx - 1], None
            return None, "ambiguous_appointment"

        # Token code match
        compact = ref.upper().replace(" ", "")
        matches = []
        for appt in _upcoming_qs(patient):
            code = appt.token_code.upper().replace(" ", "")
            if code == compact or code.replace("-", "") == compact.replace("-", ""):
                matches.append(appt)
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "ambiguous_appointment"
        return None, "appointment_not_found"

    def prepare_cancellation(appointment_ref: str) -> str:
        patient = find_patient_by_phone(ctx.phone)
        if patient is None:
            return err("appointment_not_found", "No matching appointment was found.")
        appt, problem = _resolve_appointment(patient, appointment_ref)
        if problem == "ambiguous_appointment" or (appt is None and problem == "ambiguous_appointment"):
            return err(
                "ambiguous_appointment",
                "Please specify which appointment to cancel.",
                hint=str(_short_list(patient)),
            )
        if appt is None:
            return err("appointment_not_found", "No matching appointment was found.")
        flags = cancel_flags(appt)
        if not flags["can_cancel"]:
            # Derive a stable refusal code without mutating the appointment.
            if appt.visit_started_at is not None:
                code = "visit_already_started"
                message = "The visit has already started, so this appointment cannot be cancelled."
            else:
                code = "cancel_window_closed"
                message = "Cancellations close before the appointment time."
            return err(
                code,
                message,
                hint=f"cutoff={flags['cancel_until']}; clinic_phone={ctx.clinic.phone}",
            )
        pending = {
            "type": "cancellation",
            "appointment_id": appt.id,
            "token_code": appt.token_code,
            "scheduled_at": appt.scheduled_at.isoformat(),
            "prepared_at_turn": int(session.get("turn_no") or 0),
        }
        set_pending(session, pending)
        return ok(
            {
                "confirm_summary": {
                    "doctor": f"Dr. {appt.doctor.full_name}",
                    "date_label": appt.token_date.strftime("%d %b %Y"),
                    "time_label": slot_svc.label_datetime(appt.scheduled_at),
                    "token_code": appt.token_code,
                    "note": "This frees the slot.",
                }
            }
        )

    def confirm_cancellation() -> str:
        pending = session.get("pending")
        if not pending or pending.get("type") != "cancellation":
            return err("no_pending_action", "There is no cancellation waiting for confirmation.")
        if int(pending.get("prepared_at_turn") or 0) >= int(session.get("turn_no") or 0):
            return err(
                "pending_not_confirmed",
                "Wait for the patient to confirm in a new message before cancelling.",
            )
        patient = find_patient_by_phone(ctx.phone)
        if patient is None:
            set_pending(session, None)
            return err("appointment_not_found", "No matching appointment was found.")
        try:
            appt = cancel_for_patient(
                int(pending["appointment_id"]),
                patient=patient,
                clinic=ctx.clinic,
            )
        except CancellationNotAllowed as exc:
            if exc.code in ("cancel_window_closed", "visit_already_started", "not_cancellable"):
                set_pending(session, None)
            return err(
                exc.code,
                exc.message,
                hint=f"clinic_phone={ctx.clinic.phone}",
            )
        set_pending(session, None)
        return ok(
            {
                "token_code": appt.token_code,
                "doctor": f"Dr. {appt.doctor.full_name}",
                "date_label": appt.token_date.strftime("%d %b %Y"),
                "time_label": slot_svc.label_datetime(appt.scheduled_at),
                "status": "cancelled",
            }
        )

    return [
        wrap_tool(
            "list_my_appointments",
            "List this patient's upcoming appointments at this clinic.",
            EmptyArgs,
            lambda: list_my_appointments(),
        ),
        wrap_tool(
            "prepare_cancellation",
            "Stage cancellation of one upcoming appointment for confirmation.",
            CancelPrepareArgs,
            lambda appointment_ref: prepare_cancellation(appointment_ref),
        ),
        wrap_tool(
            "confirm_cancellation",
            "Confirm the pending cancellation after the patient explicitly says yes.",
            EmptyArgs,
            lambda: confirm_cancellation(),
        ),
    ]
