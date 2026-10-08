"""Idempotent seed: Dr. Hammad Yousuf at Tawakkal Dental Clinic (Clifton DHA)."""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import (
    Clinic,
    DoctorAvailability,
    DoctorClinic,
    DoctorProfile,
    Speciality,
)

User = get_user_model()

EMAIL = "dr.hammadyousuf@patientcareapp.com"
PASSWORD = "doctor123"
CLINIC_NAME = "Tawakkal Dental Clinic"


class Command(BaseCommand):
    help = "Seed Dr. Hammad Yousuf (Dentist) at Tawakkal Dental Clinic with Mon–Sat 7pm–9pm slots."

    @transaction.atomic
    def handle(self, *args, **options):
        dentist, _ = Speciality.objects.get_or_create(
            name="Dentist", defaults={"is_active": True}
        )

        clinic, clinic_created = Clinic.objects.update_or_create(
            name=CLINIC_NAME,
            defaults={
                "address": "Clifton DHA, Karachi",
                "city": "Karachi",
                "area": "Clifton",
                "phone": "021-34567890",
                "latitude": Decimal("24.813800"),
                "longitude": Decimal("67.029900"),
                "is_active": True,
            },
        )
        self.stdout.write(
            f"Clinic {'created' if clinic_created else 'updated'}: "
            f"{clinic.name} (id={clinic.id})"
        )

        user = User.objects.filter(email__iexact=EMAIL).first()
        if user is None:
            user = User.objects.create_user(
                username=EMAIL,
                email=EMAIL,
                password=PASSWORD,
                role=User.Role.DOCTOR,
                first_name="Hammad",
                last_name="Yousuf",
            )
            user_created = True
        else:
            user.username = EMAIL
            user.email = EMAIL
            user.role = User.Role.DOCTOR
            user.first_name = "Hammad"
            user.last_name = "Yousuf"
            user.set_password(PASSWORD)
            user.save()
            user_created = False

        doctor, doctor_created = DoctorProfile.objects.update_or_create(
            user=user,
            defaults={
                "first_name": "Hammad",
                "last_name": "Yousuf",
                "clinic": clinic,
                "session_time": 30,
                "consultation_fee": Decimal("2000.00"),
                "is_active": True,
            },
        )
        doctor.specialities.set([dentist])
        self.stdout.write(
            f"Doctor {'created' if doctor_created else 'updated'}: "
            f"Dr. {doctor.full_name} (id={doctor.id})"
        )
        self.stdout.write(
            f"User {'created' if user_created else 'updated'}: {EMAIL} / {PASSWORD}"
        )

        DoctorClinic.objects.update_or_create(
            doctor=doctor,
            clinic=clinic,
            defaults={"is_primary": True},
        )

        for weekday in range(6):  # Mon–Sat
            DoctorAvailability.objects.update_or_create(
                doctor=doctor,
                clinic=clinic,
                weekday=weekday,
                specific_date=None,
                defaults={
                    "start_time": time(19, 0),
                    "end_time": time(21, 0),
                    "is_active": True,
                },
            )
        # Ensure Sunday is not left as an old open window if re-seeded.
        DoctorAvailability.objects.filter(
            doctor=doctor,
            clinic=clinic,
            weekday=6,
            specific_date=None,
        ).update(is_active=False)

        self.stdout.write("Availability: Mon–Sat 19:00–21:00 (Sunday closed)")

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
        self.stdout.write(f"doctor_id={doctor.id}")
        self.stdout.write(
            f"playground=/api/assistant/playground/?clinic_id={clinic.id}"
        )
