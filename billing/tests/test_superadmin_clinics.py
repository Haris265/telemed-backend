"""Superadmin clinic create / soft-delete API."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from catalog.models import Clinic

User = get_user_model()


class SuperadminClinicCRUDTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.superadmin = User.objects.create_user(
            username="sa_clinic_test",
            email="sa_clinic@example.com",
            password="pass12345",
            role=User.Role.SUPERADMIN,
        )
        self.payload = {
            "name": "New Test Clinic",
            "address": "Street 1",
            "city": "Karachi",
            "area": "Gulshan",
            "phone": "0211111111",
            "latitude": "24.860700",
            "longitude": "67.001100",
            "is_active": True,
        }

    def test_post_creates_clinic(self):
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.post("/api/superadmin/clinics/", self.payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "New Test Clinic")
        self.assertTrue(Clinic.objects.filter(name="New Test Clinic").exists())

    def test_post_without_lat_lng_creates_clinic(self):
        self.client.force_authenticate(user=self.superadmin)
        payload = {
            "name": "No Coords Clinic",
            "address": "Street 2",
            "city": "Karachi",
            "area": "Clifton",
            "phone": "0212222222",
            "is_active": True,
        }
        res = self.client.post("/api/superadmin/clinics/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        clinic = Clinic.objects.get(name="No Coords Clinic")
        self.assertIsNone(clinic.latitude)
        self.assertIsNone(clinic.longitude)

    def test_post_empty_string_lat_lng_treated_as_null(self):
        self.client.force_authenticate(user=self.superadmin)
        payload = {
            "name": "Blank Coords Clinic",
            "address": "Street 3",
            "city": "Karachi",
            "latitude": "",
            "longitude": "",
            "is_active": True,
        }
        res = self.client.post("/api/superadmin/clinics/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        clinic = Clinic.objects.get(name="Blank Coords Clinic")
        self.assertIsNone(clinic.latitude)
        self.assertIsNone(clinic.longitude)

    def test_post_unauthenticated_401(self):
        res = self.client.post("/api/superadmin/clinics/", self.payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_soft_deactivates(self):
        clinic = Clinic.objects.create(
            name="To Deactivate",
            address="Addr",
            city="Karachi",
            latitude="24.860700",
            longitude="67.001100",
            is_active=True,
        )
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.delete(f"/api/superadmin/clinics/{clinic.id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        clinic.refresh_from_db()
        self.assertFalse(clinic.is_active)
        self.assertTrue(Clinic.objects.filter(pk=clinic.pk).exists())

        default_list = self.client.get("/api/superadmin/clinics/")
        self.assertEqual(default_list.status_code, status.HTTP_200_OK)
        default_ids = {
            row["id"]
            for row in (
                default_list.data.get("results", default_list.data)
                if isinstance(default_list.data, dict)
                else default_list.data
            )
        }
        self.assertNotIn(clinic.id, default_ids)

        inactive_list = self.client.get("/api/superadmin/clinics/?is_active=false")
        self.assertEqual(inactive_list.status_code, status.HTTP_200_OK)
        inactive_ids = {
            row["id"]
            for row in (
                inactive_list.data.get("results", inactive_list.data)
                if isinstance(inactive_list.data, dict)
                else inactive_list.data
            )
        }
        self.assertIn(clinic.id, inactive_ids)
