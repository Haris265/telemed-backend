"""Idempotent seed: Fatimiyah Hospital consultants from October 2026 schedule PDF."""

from __future__ import annotations

import re
from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from catalog.management.commands.data.fatimiyah_oct_2026 import SCHEDULE
from catalog.models import (
    Clinic,
    DoctorAvailability,
    DoctorClinic,
    DoctorProfile,
    Speciality,
)

User = get_user_model()

CLINIC_NAME = "Fatimiyah Hospital"
PASSWORD = "doctor123"
FEE = Decimal("2000.00")
SESSION_MINS = 15
EMAIL_DOMAIN = "fatimiyah.patientcareapp.com"


def _parse_hhmm(value: str) -> time:
    parts = [int(x) for x in value.split(":")[:2]]
    return time(parts[0] % 24, parts[1])


def _doctor_key(first_name: str, last_name: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        f"{(first_name or '').strip()} {(last_name or '').strip()}".strip().lower(),
    )


def _merge_schedule(rows: list[dict]) -> list[dict]:
    """Merge duplicate people across specialities into one doctor record."""
    merged: dict[str, dict] = {}
    for row in rows:
        key = _doctor_key(row["first_name"], row["last_name"])
        if not key:
            continue
        if key not in merged:
            merged[key] = {
                "first_name": row["first_name"].strip(),
                "last_name": (row.get("last_name") or "").strip(),
                "specialities": set(),
                "windows": [],
            }
        entry = merged[key]
        entry["specialities"].add(row["speciality"])
        for win in row.get("windows") or []:
            signature = (
                tuple(sorted(win["weekdays"])),
                win["start"],
                win["end"],
            )
            if signature not in {
                (tuple(sorted(w["weekdays"])), w["start"], w["end"])
                for w in entry["windows"]
            }:
                entry["windows"].append(
                    {
                        "weekdays": list(win["weekdays"]),
                        "start": win["start"],
                        "end": win["end"],
                    }
                )
    return list(merged.values())


def _email_for(first_name: str, last_name: str) -> str:
    base = slugify(f"{first_name} {last_name}".strip()) or "doctor"
    return f"dr.{base}@{EMAIL_DOMAIN}"


class Command(BaseCommand):
    help = (
        "Seed Fatimiyah Hospital clinic, consultants, and weekly availability "
        "from the October 2026 consultant schedule (fee 2000, session 15)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        doctors = _merge_schedule(SCHEDULE)
        clinic, clinic_created = Clinic.objects.update_or_create(
            name=CLINIC_NAME,
            defaults={
                "address": "Fatimiyah Hospital, Karachi",
                "city": "Karachi",
                "area": "Karachi",
                "phone": "021-111-000-000",
                "latitude": Decimal("24.860700"),
                "longitude": Decimal("67.001100"),
                "is_active": True,
            },
        )
        self.stdout.write(
            f"Clinic {'created' if clinic_created else 'updated'}: "
            f"{clinic.name} (id={clinic.id})"
        )

        avail_count = 0
        for row in doctors:
            first = row["first_name"]
            last = row["last_name"] or first
            email = _email_for(first, last)

            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                # Avoid username collisions on slug edge cases.
                username = email
                if User.objects.filter(username=username).exists():
                    username = f"{username}.{clinic.id}"
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=PASSWORD,
                    role=User.Role.DOCTOR,
                    first_name=first[:150],
                    last_name=last[:150],
                )
            else:
                user.email = email
                user.role = User.Role.DOCTOR
                user.first_name = first[:150]
                user.last_name = last[:150]
                user.set_password(PASSWORD)
                user.save()

            doctor, _ = DoctorProfile.objects.update_or_create(
                user=user,
                defaults={
                    "first_name": first[:100],
                    "last_name": last[:100],
                    "clinic": clinic,
                    "session_time": SESSION_MINS,
                    "consultation_fee": FEE,
                    "is_active": True,
                },
            )

            specs = []
            for name in sorted(row["specialities"]):
                spec, _ = Speciality.objects.get_or_create(
                    name=name, defaults={"is_active": True}
                )
                specs.append(spec)
            doctor.specialities.set(specs)

            DoctorClinic.objects.update_or_create(
                doctor=doctor,
                clinic=clinic,
                defaults={"is_primary": True},
            )

            # Replace weekly windows for this doctor at this clinic.
            DoctorAvailability.objects.filter(
                doctor=doctor,
                clinic=clinic,
                specific_date=None,
            ).delete()

            for win in row["windows"]:
                start = _parse_hhmm(win["start"])
                end = _parse_hhmm(win["end"])
                for weekday in sorted(set(win["weekdays"])):
                    DoctorAvailability.objects.create(
                        doctor=doctor,
                        clinic=clinic,
                        weekday=weekday,
                        specific_date=None,
                        start_time=start,
                        end_time=end,
                        is_active=True,
                    )
                    avail_count += 1

        try:
            from assistant.models import AssistantPlan, ClinicAssistantConfig

            plan = AssistantPlan.objects.filter(code="A").first()
            if plan is None:
                self.stdout.write(
                    self.style.WARNING(
                        "Assistant plan A missing; skip ClinicAssistantConfig"
                    )
                )
            else:
                cfg, cfg_created = ClinicAssistantConfig.objects.update_or_create(
                    clinic=clinic,
                    defaults={"plan": plan, "is_enabled": True},
                )
                self.stdout.write(
                    f"Assistant config {'created' if cfg_created else 'updated'}: "
                    f"enabled={cfg.is_enabled} plan={cfg.plan.code}"
                )
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f"Could not enable assistant config: {exc}")
            )

        self.stdout.write(self.style.SUCCESS("Done."))
        self.stdout.write(f"clinic_id={clinic.id}")
        self.stdout.write(f"doctors={len(doctors)}")
        self.stdout.write(f"availability_rows={avail_count}")
        self.stdout.write(f"default_password={PASSWORD}")
        self.stdout.write(
            f"playground=/api/assistant/playground/?clinic_id={clinic.id}"
        )
