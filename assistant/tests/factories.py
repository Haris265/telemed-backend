"""Test factories for clinics, doctors, availability, and assistant config."""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model

from appointments.models import Appointment
from appointments.services import pakistan_today
from assistant.models import AssistantPlan, ClinicAssistantConfig
from catalog.models import Clinic, DoctorAvailability, DoctorClinic, DoctorProfile, Speciality
from patients.models import PatientProfile

User = get_user_model()


def make_user(username: str, *, role: str = "doctor"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass12345",
        role=role,
    )


def make_clinic(name: str = "Alpha Clinic", **kwargs) -> Clinic:
    defaults = {
        "address": "Street 1",
        "city": "Karachi",
        "area": "Gulshan",
        "phone": "0211111111",
        "latitude": Decimal("24.860700"),
        "longitude": Decimal("67.001100"),
        "is_active": True,
    }
    defaults.update(kwargs)
    return Clinic.objects.create(name=name, **defaults)


def make_speciality(name: str = "Cardiology") -> Speciality:
    obj, _ = Speciality.objects.get_or_create(name=name, defaults={"is_active": True})
    return obj


def make_doctor(
    *,
    username: str,
    first_name: str = "Ali",
    last_name: str = "Khan",
    clinic: Clinic | None = None,
    specialities: list[Speciality] | None = None,
    fee: str = "2000.00",
    session_time: int = 30,
) -> DoctorProfile:
    user = make_user(username)
    doctor = DoctorProfile.objects.create(
        user=user,
        first_name=first_name,
        last_name=last_name,
        clinic=clinic,
        consultation_fee=Decimal(fee),
        session_time=session_time,
        is_active=True,
    )
    if clinic is not None:
        DoctorClinic.objects.get_or_create(doctor=doctor, clinic=clinic, defaults={"is_primary": True})
    for spec in specialities or []:
        doctor.specialities.add(spec)
    return doctor


def link_doctor_clinic(doctor: DoctorProfile, clinic: Clinic, *, primary: bool = False):
    return DoctorClinic.objects.get_or_create(
        doctor=doctor, clinic=clinic, defaults={"is_primary": primary}
    )[0]


def seed_week_availability(doctor: DoctorProfile, clinic: Clinic):
    for weekday in range(7):
        DoctorAvailability.objects.update_or_create(
            doctor=doctor,
            clinic=clinic,
            weekday=weekday,
            specific_date=None,
            defaults={
                "start_time": time(9, 0),
                "end_time": time(17, 0),
                "is_active": True,
            },
        )


def ensure_plan(code: str = "A") -> AssistantPlan:
    plan, _ = AssistantPlan.objects.get_or_create(
        code=code,
        defaults={
            "name": {"A": "Starter", "B": "Standard", "C": "Premium"}.get(code, code),
            "max_bot_replies_per_patient_month": {"A": 10, "B": 20, "C": 30}.get(code, 10),
            "max_text_messages_per_day": {"A": 60, "B": 150, "C": 400}.get(code, 60),
            "max_voice_notes_per_day": {"A": 15, "B": 40, "C": 100}.get(code, 15),
            "is_active": True,
        },
    )
    return plan


def enable_assistant(clinic: Clinic, *, plan_code: str = "A") -> ClinicAssistantConfig:
    plan = ensure_plan(plan_code)
    config, _ = ClinicAssistantConfig.objects.update_or_create(
        clinic=clinic,
        defaults={"plan": plan, "is_enabled": True},
    )
    return config


def make_patient(phone: str, name: str = "Test Patient") -> PatientProfile:
    return PatientProfile.objects.create(phone=phone, name=name)


def make_appointment(
    *,
    patient: PatientProfile,
    doctor: DoctorProfile,
    clinic: Clinic,
    scheduled_at,
    token_number: int = 1,
    status: str = Appointment.Status.UPCOMING,
) -> Appointment:
    return Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        clinic=clinic,
        scheduled_at=scheduled_at,
        token_date=scheduled_at.date() if hasattr(scheduled_at, "date") else pakistan_today(),
        token_number=token_number,
        status=status,
        notes="",
    )
