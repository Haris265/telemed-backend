"""Parent-layer tools: multi-clinic list/select/switch and cross-clinic appointments."""

from __future__ import annotations

from pydantic import BaseModel, Field

from appointments.models import Appointment
from appointments.services import pakistan_today

from assistant.eligibility import clinic_list_rows, is_clinic_eligible, resolve_eligible_clinic
from assistant.parent_session import (
    clear_selected_clinic,
    resolve_parent_ref,
    select_clinic_on_parent,
    set_parent_refs,
)
from assistant.services.cancellation import cancel_flags
from assistant.services.patients import find_patient_by_phone
from assistant.services import slots as slot_svc


class EmptyArgs(BaseModel):
    pass


class ClinicRefArgs(BaseModel):
    clinic_ref: str = Field(
        ...,
        description=(
            "Clinic id, 1-based list number from the last list_clinics result, "
            "or clinic name substring."
        ),
    )


def build_parent_discovery_tools(parent_session: dict):
    from . import err, ok, wrap_tool

    def list_clinics() -> str:
        rows = clinic_list_rows()
        refs = [
            {
                "n": r["n"],
                "kind": "clinic",
                "id": r["clinic_id"],
                "label": r["name"],
            }
            for r in rows
        ]
        set_parent_refs(parent_session, refs)
        return ok({"clinics": rows, "count": len(rows)})

    def _resolve_clinic_id(clinic_ref: str) -> int | None:
        ref = (clinic_ref or "").strip()
        if not ref:
            return None
        if ref.isdigit():
            n = int(ref)
            found = resolve_parent_ref(parent_session, n)
            if found and found.get("kind") == "clinic":
                return int(found["id"])
            # Treat as clinic_id if eligible
            if is_clinic_eligible(n):
                return n
            # Or 1-based index into current eligible list
            rows = clinic_list_rows()
            if 1 <= n <= len(rows):
                return int(rows[n - 1]["clinic_id"])
            return None
        # Name substring (case-insensitive)
        needle = ref.lower()
        matches = [
            r for r in clinic_list_rows() if needle in (r["name"] or "").lower()
        ]
        if len(matches) == 1:
            return int(matches[0]["clinic_id"])
        return None

    def select_clinic(clinic_ref: str) -> str:
        clinic_id = _resolve_clinic_id(clinic_ref)
        if clinic_id is None:
            return err(
                "clinic_not_found",
                "Could not identify that clinic. Call list_clinics and pick one.",
            )
        clinic = resolve_eligible_clinic(clinic_id)
        if clinic is None:
            return err(
                "clinic_not_eligible",
                "That clinic is not available in this assistant.",
            )
        select_clinic_on_parent(parent_session, clinic.id, clear_previous=True)
        return ok(
            {
                "selected_clinic_id": clinic.id,
                "name": clinic.name,
                "area": clinic.area or "",
                "address": clinic.address or "",
                "city": clinic.city or "",
                "phone": clinic.phone or "",
                "hint": (
                    "Clinic selected. On the next patient message you will use this "
                    "clinic's doctors, slots, booking, and cancellation tools."
                ),
            }
        )

    def switch_clinic(clinic_ref: str) -> str:
        """Switch to another clinic, or clear selection with clinic_ref='clear'."""
        raw = (clinic_ref or "").strip().lower()
        if raw in ("clear", "none", "reset", "-"):
            clear_selected_clinic(parent_session)
            return ok(
                {
                    "selected_clinic_id": None,
                    "hint": "Clinic selection cleared. Call list_clinics to choose again.",
                }
            )
        return select_clinic(clinic_ref)

    def list_my_appointments_all() -> str:
        patient = find_patient_by_phone(parent_session["phone"])
        if patient is None:
            set_parent_refs(parent_session, [])
            return ok({"appointments": []})
        eligible_ids = {r["clinic_id"] for r in clinic_list_rows()}
        qs = (
            Appointment.objects.filter(
                patient=patient,
                status=Appointment.Status.UPCOMING,
                token_date__gte=pakistan_today(),
                clinic_id__in=eligible_ids,
            )
            .select_related("doctor", "clinic")
            .order_by("token_date", "token_number")[:10]
        )
        rows = []
        refs = []
        for i, appt in enumerate(qs, start=1):
            flags = cancel_flags(appt)
            rows.append(
                {
                    "n": i,
                    "appointment_id": appt.id,
                    "token_code": appt.token_code,
                    "clinic_id": appt.clinic_id,
                    "clinic_name": appt.clinic.name,
                    "doctor": f"Dr. {appt.doctor.full_name}",
                    "date": appt.token_date.isoformat(),
                    "date_label": appt.token_date.strftime("%d %b %Y"),
                    "time_label": slot_svc.label_datetime(appt.scheduled_at),
                    "status": appt.status,
                    "can_cancel": flags["can_cancel"],
                    "cancel_until": flags["cancel_until"],
                }
            )
            refs.append(
                {
                    "n": i,
                    "kind": "appointment",
                    "id": appt.id,
                    "clinic_id": appt.clinic_id,
                    "label": appt.token_code,
                    "token_code": appt.token_code,
                }
            )
        set_parent_refs(parent_session, refs)
        return ok(
            {
                "appointments": rows,
                "hint": (
                    "To cancel, select_clinic with that appointment's clinic_id "
                    "(or name), then use prepare_cancellation / confirm_cancellation."
                ),
            }
        )

    return [
        wrap_tool(
            "list_clinics",
            "List clinics available in this multi-clinic assistant (name, area, address).",
            EmptyArgs,
            lambda: list_clinics(),
        ),
        wrap_tool(
            "select_clinic",
            "Select one clinic by id, list number, or name. Required before booking at a clinic.",
            ClinicRefArgs,
            lambda clinic_ref: select_clinic(clinic_ref),
        ),
        wrap_tool(
            "switch_clinic",
            "Switch to another clinic (same as select) or pass 'clear' to unset selection.",
            ClinicRefArgs,
            lambda clinic_ref: switch_clinic(clinic_ref),
        ),
        wrap_tool(
            "list_my_appointments_all",
            "List this patient's upcoming appointments across all eligible clinics.",
            EmptyArgs,
            lambda: list_my_appointments_all(),
        ),
    ]
