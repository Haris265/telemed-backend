"""Clinic admin appointment list/detail API."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import ClinicAdminProfile
from assistant.tests.factories import (
    make_appointment,
    make_clinic,
    make_doctor,
    make_patient,
)

User = get_user_model()
PK_TZ = ZoneInfo("Asia/Karachi")


def _make_clinic_admin(username: str, clinic) -> User:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass12345",
        role=User.Role.CLINIC_ADMIN,
    )
    ClinicAdminProfile.objects.create(user=user, clinic=clinic)
    return user


def _slot(days: int = 1, hour: int = 10) -> datetime:
    day = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(day, time(hour, 0)), PK_TZ)


class ClinicAppointmentAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.clinic_a = make_clinic(name="Clinic A Appt")
        self.clinic_b = make_clinic(name="Clinic B Appt")
        self.doc_a = make_doctor(username="doc_appt_a", clinic=self.clinic_a)
        self.doc_b = make_doctor(username="doc_appt_b", clinic=self.clinic_b)
        self.patient_a = make_patient("03001110001", "Patient A")
        self.patient_b = make_patient("03001110002", "Patient B")
        self.appt_a = make_appointment(
            patient=self.patient_a,
            doctor=self.doc_a,
            clinic=self.clinic_a,
            scheduled_at=_slot(1, 10),
            token_number=1,
        )
        self.appt_b = make_appointment(
            patient=self.patient_b,
            doctor=self.doc_b,
            clinic=self.clinic_b,
            scheduled_at=_slot(1, 11),
            token_number=1,
        )
        self.admin_a = _make_clinic_admin("clinic_admin_appt_a", self.clinic_a)
        self.admin_b = _make_clinic_admin("clinic_admin_appt_b", self.clinic_b)
        self.platform_admin = User.objects.create_user(
            username="platform_admin_appt",
            email="platform_appt@example.com",
            password="pass12345",
            role=User.Role.ADMIN,
        )

    def test_unauthenticated_returns_401(self):
        res = self.client.get("/api/clinic/appointments/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_platform_admin_without_clinic_profile_returns_403(self):
        self.client.force_authenticate(user=self.platform_admin)
        res = self.client.get("/api/clinic/appointments/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_clinic_admin_sees_only_own_clinic_appointments(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get("/api/clinic/appointments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        ids = {row["id"] for row in results}
        self.assertEqual(ids, {self.appt_a.id})
        self.assertNotIn(self.appt_b.id, ids)

    def test_other_clinic_cannot_retrieve_appointment(self):
        self.client.force_authenticate(user=self.admin_b)
        res = self.client.get(f"/api/clinic/appointments/{self.appt_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_own_clinic_can_retrieve_appointment(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get(f"/api/clinic/appointments/{self.appt_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.appt_a.id)

    def test_q_filter(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get("/api/clinic/appointments/", {"q": "Patient A"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.appt_a.id)
