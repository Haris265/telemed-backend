"""Idempotent demo appointments + commission for Fatimiyah Hospital."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment
from appointments.services import pakistan_today
from catalog.models import Clinic, DoctorAvailability, DoctorClinic, DoctorProfile
from patients.models import PatientProfile

CLINIC_NAME = "Fatimiyah Hospital"
PK_TZ = ZoneInfo("Asia/Karachi")
FEE = Decimal("2000.00")
COMMISSION = Decimal("20.00")

DEMO_PATIENTS = [
    ("03001234001", "Ahmed Raza"),
    ("03001234002", "Fatima Noor"),
    ("03001234003", "Hassan Ali"),
    ("03001234004", "Ayesha Khan"),
    ("03001234005", "Bilal Sheikh"),
    ("03001234006", "Sana Malik"),
    ("03001234007", "Omar Farooq"),
    ("03001234008", "Zainab Hussain"),
]


def _aware(day, hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), PK_TZ)


class Command(BaseCommand):
    help = (
        "Seed Fatimiyah demo patients/appointments and set 20% clinic commission "
        "on DoctorClinic links."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        clinic = Clinic.objects.filter(name=CLINIC_NAME).first()
        if clinic is None:
            self.stderr.write(self.style.ERROR(f"Clinic not found: {CLINIC_NAME}"))
            return

        updated = DoctorClinic.objects.filter(clinic=clinic).update(
            commission_type=DoctorClinic.CommissionType.PERCENTAGE,
            commission_value=COMMISSION,
            commission_updated_at=timezone.now(),
        )
        self.stdout.write(f"DoctorClinic commission updated: {updated}")

        doctors = list(
            DoctorProfile.objects.filter(
                doctor_clinics__clinic=clinic,
                is_active=True,
                availabilities__clinic=clinic,
                availabilities__is_active=True,
                availabilities__specific_date__isnull=True,
            )
            .distinct()
            .order_by("id")[:5]
        )
        if not doctors:
            self.stderr.write(self.style.ERROR("No Fatimiyah doctors with availability"))
            return

        patients = []
        for phone, name in DEMO_PATIENTS:
            patient, _ = PatientProfile.objects.update_or_create(
                phone=phone,
                defaults={"name": name},
            )
            patients.append(patient)

        today = pakistan_today()
        specs = [
            # (patient_idx, doctor_idx, day_offset, hour, status, paid)
            (0, 0, -2, 12, Appointment.Status.COMPLETED, True),
            (1, 0, -1, 12, Appointment.Status.COMPLETED, True),
            (2, 0, 1, 12, Appointment.Status.UPCOMING, False),
            (3, 1, -3, 16, Appointment.Status.COMPLETED, True),
            (4, 1, 0, 16, Appointment.Status.UPCOMING, False),
            (5, 2, -4, 10, Appointment.Status.CANCELLED, False),
            (6, 2, 2, 10, Appointment.Status.UPCOMING, False),
            (0, 3, -5, 15, Appointment.Status.COMPLETED, True),
            (7, 3, 3, 15, Appointment.Status.UPCOMING, False),
            (1, 4, -1, 11, Appointment.Status.COMPLETED, False),
            (2, 4, 4, 11, Appointment.Status.UPCOMING, False),
            (3, 0, -6, 13, Appointment.Status.COMPLETED, True),
        ]

        created = updated_appts = 0
        for p_idx, d_idx, day_off, hour, status, paid in specs:
            doctor = doctors[d_idx % len(doctors)]
            patient = patients[p_idx]
            day = today + timedelta(days=day_off)
            # Prefer a weekday the doctor actually works when possible.
            avail = (
                DoctorAvailability.objects.filter(
                    doctor=doctor,
                    clinic=clinic,
                    is_active=True,
                    specific_date=None,
                    weekday=day.weekday(),
                )
                .order_by("start_time")
                .first()
            )
            if avail:
                hour = avail.start_time.hour
                minute = avail.start_time.minute
            else:
                minute = 0
            scheduled = _aware(day, hour, minute)
            token_number = 9000 + (p_idx * 10) + d_idx + abs(day_off)

            defaults = {
                "patient": patient,
                "clinic": clinic,
                "scheduled_at": scheduled,
                "status": status,
                "notes": "Fatimiyah demo appointment",
                "payment_method": Appointment.PaymentMethod.CASH_AT_CLINIC,
                "payment_amount_expected": FEE,
                "payment_status": (
                    Appointment.PaymentStatus.PAID
                    if paid
                    else Appointment.PaymentStatus.PENDING
                ),
                "payment_amount_received": FEE if paid else None,
            }
            # Unique on (doctor, token_date, token_number)
            obj, was_created = Appointment.objects.update_or_create(
                doctor=doctor,
                token_date=day,
                token_number=token_number,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated_appts += 1

        self.stdout.write(self.style.SUCCESS("Done."))
        self.stdout.write(f"clinic_id={clinic.id}")
        self.stdout.write(f"doctors_used={len(doctors)}")
        self.stdout.write(f"appointments_created={created}")
        self.stdout.write(f"appointments_updated={updated_appts}")
