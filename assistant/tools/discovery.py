"""Discovery tools: specialities and doctors at this clinic."""

from __future__ import annotations

from pydantic import BaseModel, Field

from assistant import settings_access as sa
from assistant.context import ClinicContext
from assistant.repo import ClinicCatalogRepo
from assistant.services import slots as slot_svc
from assistant.session_store import set_refs


class EmptyArgs(BaseModel):
    pass


class SpecialityArgs(BaseModel):
    speciality_id: int = Field(..., gt=0)


class SearchArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=100)


def build_discovery_tools(ctx: ClinicContext, session: dict):
    from . import err, ok, wrap_tool

    repo = ClinicCatalogRepo(ctx.clinic)

    def list_specialities() -> str:
        return ok(repo.list_specialities())

    def get_speciality_overview(speciality_id: int) -> str:
        specs = {s["speciality_id"]: s for s in repo.list_specialities()}
        if speciality_id not in specs:
            return err("speciality_not_found", "That speciality is not available at this clinic.")
        doctors = repo.doctors_for_speciality(speciality_id)
        max_docs = sa.max_doctors_per_overview()
        more = max(0, len(doctors) - max_docs)
        rows = []
        refs = []
        for i, doc in enumerate(doctors[:max_docs], start=1):
            next_slots = slot_svc.sample_next_slots(
                doc,
                ctx.clinic,
                dates=sa.overview_dates(),
                slots_per_date=sa.overview_slots_per_date(),
            )
            row = {
                "doctor_id": doc.id,
                "name": f"Dr. {doc.full_name}",
                "fee": str(doc.consultation_fee),
                "session_minutes": int(doc.session_time or 15),
                "specialities": [s.name for s in doc.specialities.all()],
                "next_slots": next_slots,
            }
            rows.append(row)
            refs.append(
                {"n": i, "kind": "doctor", "id": doc.id, "label": f"Dr. {doc.full_name}"}
            )
        set_refs(session, refs)
        return ok(
            {
                "speciality": specs[speciality_id],
                "doctors": rows,
                "more_doctors": more,
            }
        )

    def search_doctors(query: str) -> str:
        doctors = repo.search_doctors(query, limit=5)
        refs = []
        rows = []
        for i, doc in enumerate(doctors, start=1):
            rows.append(
                {
                    "doctor_id": doc.id,
                    "name": f"Dr. {doc.full_name}",
                    "fee": str(doc.consultation_fee),
                    "session_minutes": int(doc.session_time or 15),
                    "specialities": [s.name for s in doc.specialities.all()],
                }
            )
            refs.append(
                {"n": i, "kind": "doctor", "id": doc.id, "label": f"Dr. {doc.full_name}"}
            )
        set_refs(session, refs)
        return ok({"doctors": rows})

    return [
        wrap_tool(
            "list_specialities",
            "List specialities available at this clinic with doctor counts.",
            EmptyArgs,
            lambda: list_specialities(),
        ),
        wrap_tool(
            "get_speciality_overview",
            "Rich overview of doctors for a speciality at this clinic, with sample next slots.",
            SpecialityArgs,
            lambda speciality_id: get_speciality_overview(speciality_id),
        ),
        wrap_tool(
            "search_doctors",
            "Search doctors at this clinic by name.",
            SearchArgs,
            lambda query: search_doctors(query),
        ),
    ]
