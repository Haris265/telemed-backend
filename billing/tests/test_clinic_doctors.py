"""Clinic admin doctor roster API."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import ClinicAdminProfile
from assistant.tests.factories import make_clinic, make_doctor, make_speciality

User = get_user_model()


def _make_clinic_admin(username: str, clinic) -> User:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass12345",
        role=User.Role.CLINIC_ADMIN,
    )
    ClinicAdminProfile.objects.create(user=user, clinic=clinic)
    return user


class ClinicDoctorListTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.clinic_a = make_clinic(name="Clinic A")
        self.clinic_b = make_clinic(name="Clinic B")
        self.spec = make_speciality("Cardiology")
        self.doc_a1 = make_doctor(
            username="doc_a1",
            first_name="Ali",
            last_name="A",
            clinic=self.clinic_a,
            specialities=[self.spec],
        )
        self.doc_a2 = make_doctor(
            username="doc_a2",
            first_name="Bina",
            last_name="A",
            clinic=self.clinic_a,
        )
        self.doc_b = make_doctor(
            username="doc_b",
            first_name="Carl",
            last_name="B",
            clinic=self.clinic_b,
        )
        self.admin_a = _make_clinic_admin("admin_a", self.clinic_a)
        self.admin_b = _make_clinic_admin("admin_b", self.clinic_b)
        self.platform_admin = User.objects.create_user(
            username="platform_admin",
            email="platform@example.com",
            password="pass12345",
            role=User.Role.ADMIN,
        )

    def test_unauthenticated_returns_401(self):
        res = self.client.get("/api/clinic/doctors/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_platform_admin_without_clinic_profile_returns_403(self):
        self.client.force_authenticate(user=self.platform_admin)
        res = self.client.get("/api/clinic/doctors/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_clinic_admin_sees_only_own_clinic_doctors(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get("/api/clinic/doctors/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        ids = {row["id"] for row in results}
        self.assertEqual(ids, {self.doc_a1.id, self.doc_a2.id})
        self.assertNotIn(self.doc_b.id, ids)

    def test_other_clinic_admin_tenancy(self):
        self.client.force_authenticate(user=self.admin_b)
        res = self.client.get("/api/clinic/doctors/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        ids = {row["id"] for row in results}
        self.assertEqual(ids, {self.doc_b.id})

    def test_q_filter(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get("/api/clinic/doctors/", {"q": "Ali"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.doc_a1.id)

    def test_speciality_filter(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get(
            "/api/clinic/doctors/", {"speciality": self.spec.id}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.doc_a1.id)

    def test_inactive_doctor_excluded(self):
        self.doc_a2.is_active = False
        self.doc_a2.save(update_fields=["is_active"])
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get("/api/clinic/doctors/")
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        ids = {row["id"] for row in results}
        self.assertEqual(ids, {self.doc_a1.id})

    def test_detail_unauthenticated_returns_401(self):
        res = self.client.get(f"/api/clinic/doctors/{self.doc_a1.uuid}/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detail_own_clinic_returns_200(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get(f"/api/clinic/doctors/{self.doc_a1.uuid}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["uuid"], str(self.doc_a1.uuid))
        self.assertEqual(res.data["id"], self.doc_a1.id)

    def test_detail_other_clinic_returns_404(self):
        self.client.force_authenticate(user=self.admin_b)
        res = self.client.get(f"/api/clinic/doctors/{self.doc_a1.uuid}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
