"""Clinic-scoped catalog reads. Tools must use this module, not catalog.models."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Q, QuerySet

from catalog.models import Clinic, DoctorClinic, DoctorProfile, Speciality


@dataclass(frozen=True)
class ClinicCatalogRepo:
    clinic: Clinic

    def doctors_qs(self) -> QuerySet[DoctorProfile]:
        if not self.clinic.is_active:
            return DoctorProfile.objects.none()
        return (
            DoctorProfile.objects.filter(
                is_active=True,
                doctor_clinics__clinic=self.clinic,
            )
            .prefetch_related("specialities")
            .distinct()
            .order_by("first_name", "last_name")
        )

    def get_doctor(self, doctor_id: int) -> DoctorProfile | None:
        return self.doctors_qs().filter(pk=doctor_id).first()

    def doctor_in_clinic(self, doctor_id: int) -> bool:
        return DoctorClinic.objects.filter(
            doctor_id=doctor_id,
            doctor__is_active=True,
            clinic=self.clinic,
            clinic__is_active=True,
        ).exists()

    def list_specialities(self) -> list[dict]:
        rows = (
            Speciality.objects.filter(
                is_active=True,
                doctors__is_active=True,
                doctors__doctor_clinics__clinic=self.clinic,
            )
            .annotate(
                doctor_count=Count(
                    "doctors",
                    filter=Q(
                        doctors__is_active=True,
                        doctors__doctor_clinics__clinic=self.clinic,
                    ),
                    distinct=True,
                )
            )
            .filter(doctor_count__gt=0)
            .order_by("name")
        )
        return [
            {
                "speciality_id": s.id,
                "name": s.name,
                "doctor_count": s.doctor_count,
            }
            for s in rows
        ]

    def doctors_for_speciality(self, speciality_id: int) -> list[DoctorProfile]:
        return list(
            self.doctors_qs()
            .filter(specialities__id=speciality_id)
            .distinct()
        )

    def search_doctors(self, query: str, *, limit: int = 5) -> list[DoctorProfile]:
        q = (query or "").strip()
        if not q:
            return []
        return list(
            self.doctors_qs()
            .filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(first_name__icontains=q.split()[0])
            )[:limit]
        )

    def clinic_facts(self, *, max_doctors: int = 40) -> dict:
        doctors = list(self.doctors_qs()[: max_doctors + 1])
        truncated = len(doctors) > max_doctors
        doctors = doctors[:max_doctors]
        by_speciality: dict[str, list[dict]] = {}
        for doc in doctors:
            specs = list(doc.specialities.all())
            if not specs:
                key = "General"
                by_speciality.setdefault(key, []).append(self._doctor_row(doc))
                continue
            for spec in specs:
                by_speciality.setdefault(spec.name, []).append(
                    self._doctor_row(doc, speciality_id=spec.id)
                )
        return {
            "clinic_id": self.clinic.id,
            "name": self.clinic.name,
            "address": self.clinic.address,
            "area": self.clinic.area,
            "city": self.clinic.city,
            "phone": self.clinic.phone,
            "truncated": truncated,
            "specialities": by_speciality,
            "speciality_counts": self.list_specialities() if truncated else None,
        }

    @staticmethod
    def _doctor_row(doc: DoctorProfile, *, speciality_id: int | None = None) -> dict:
        row = {
            "doctor_id": doc.id,
            "name": f"Dr. {doc.full_name}",
            "fee": str(doc.consultation_fee),
            "session_minutes": int(doc.session_time or 15),
            "specialities": [s.name for s in doc.specialities.all()],
        }
        if speciality_id is not None:
            row["speciality_id"] = speciality_id
        return row
