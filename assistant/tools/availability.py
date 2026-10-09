"""Doctor availability tool."""

from __future__ import annotations

from pydantic import BaseModel, Field

from assistant.context import ClinicContext
from assistant.repo import ClinicCatalogRepo
from assistant.services import slots as slot_svc


class AvailabilityArgs(BaseModel):
    doctor_id: int = Field(..., gt=0)
    date: str | None = Field(
        default=None,
        description="Optional ISO date YYYY-MM-DD. Omit for next available dates.",
    )


def build_availability_tools(ctx: ClinicContext, session: dict):
    from . import err, ok, wrap_tool

    repo = ClinicCatalogRepo(ctx.clinic)

    def get_doctor_availability(doctor_id: int, date: str | None = None) -> str:
        doctor = repo.get_doctor(doctor_id)
        if doctor is None:
            return err("not_in_clinic", "That doctor is not available at this clinic.")
        if not doctor.is_active:
            return err("doctor_inactive", "That doctor is currently inactive.")
        if date:
            try:
                token_date = __import__("datetime").date.fromisoformat(date)
            except ValueError:
                return err("invalid_argument", "date must be YYYY-MM-DD.")
            times = slot_svc.open_times_for_date(doctor, ctx.clinic, token_date)
            return ok(
                {
                    "doctor_id": doctor.id,
                    "doctor_name": f"Dr. {doctor.full_name}",
                    "date": token_date.isoformat(),
                    "times": times[:24],
                }
            )
        dates = slot_svc.next_available_dates(doctor, ctx.clinic, limit=5)
        return ok(
            {
                "doctor_id": doctor.id,
                "doctor_name": f"Dr. {doctor.full_name}",
                "dates": dates,
            }
        )

    return [
        wrap_tool(
            "get_doctor_availability",
            "Return open dates or exact bookable times for one doctor at this clinic. "
            "The times in the result are the only appointment times you may offer. "
            "Do not present a clinic opening window as the appointment time.",
            AvailabilityArgs,
            lambda doctor_id, date=None: get_doctor_availability(doctor_id, date),
        )
    ]
