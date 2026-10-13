"""Enriched clinic doctor detail + commission PATCH."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import ClinicAdminProfile
from appointments.models import Appointment
from assistant.tests.factories import (
    make_appointment,
    make_clinic,
    make_doctor,
    make_patient,
    seed_week_availability,
)
from catalog.models import DoctorClinic

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


class ClinicDoctorDetailEnrichmentTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.clinic_a = make_clinic(name="Detail Clinic A")
        self.clinic_b = make_clinic(name="Detail Clinic B")
        self.doc_a = make_doctor(
            username="detail_doc_a",
            first_name="Ali",
            last_name="Detail",
            clinic=self.clinic_a,
            fee="2000.00",
            session_time=15,
        )
        self.doc_b = make_doctor(
            username="detail_doc_b",
            clinic=self.clinic_b,
            fee="1500.00",
        )
        seed_week_availability(self.doc_a, self.clinic_a)
        link = DoctorClinic.objects.get(doctor=self.doc_a, clinic=self.clinic_a)
        link.commission_type = DoctorClinic.CommissionType.PERCENTAGE
        link.commission_value = Decimal("20.00")
        link.save(update_fields=["commission_type", "commission_value"])

        self.patient = make_patient("03009990001", "Detail Patient")
        self.appt = make_appointment(
            patient=self.patient,
            doctor=self.doc_a,
            clinic=self.clinic_a,
            scheduled_at=_slot(-1, 10),
            token_number=1,
            status=Appointment.Status.COMPLETED,
        )
        self.appt.payment_status = Appointment.PaymentStatus.PAID
        self.appt.payment_amount_expected = Decimal("2000.00")
        self.appt.payment_amount_received = Decimal("2000.00")
        self.appt.payment_method = Appointment.PaymentMethod.CASH_AT_CLINIC
        self.appt.save()

        self.admin_a = _make_clinic_admin("detail_admin_a", self.clinic_a)
        self.admin_b = _make_clinic_admin("detail_admin_b", self.clinic_b)

    def test_detail_includes_nested_blocks(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.get(f"/api/clinic/doctors/{self.doc_a.uuid}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for key in (
            "clinic_link",
            "availability",
            "upcoming_slots",
            "stats",
            "patients",
            "appointments",
        ):
            self.assertIn(key, res.data)
        self.assertEqual(res.data["clinic_link"]["commission_value"], "20.00")
        self.assertEqual(res.data["stats"]["completed_count"], 1)
        self.assertEqual(res.data["stats"]["clinic_commission_total"], "400.00")
        self.assertEqual(res.data["stats"]["doctor_earnings_total"], "1600.00")
        self.assertEqual(len(res.data["appointments"]), 1)
        self.assertEqual(res.data["appointments"][0]["clinic_share"], "400.00")
        self.assertTrue(len(res.data["availability"]["weekly"]) >= 1)

    def test_other_clinic_detail_404(self):
        self.client.force_authenticate(user=self.admin_b)
        res = self.client.get(f"/api/clinic/doctors/{self.doc_a.uuid}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_commission_updates_shares(self):
        self.client.force_authenticate(user=self.admin_a)
        res = self.client.patch(
            f"/api/clinic/doctors/{self.doc_a.uuid}/",
            {"commission_type": "percentage", "commission_value": "25.00"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["clinic_link"]["commission_value"], "25.00")
        self.assertEqual(res.data["appointments"][0]["clinic_share"], "500.00")
        self.assertEqual(res.data["appointments"][0]["doctor_share"], "1500.00")
        link = DoctorClinic.objects.get(doctor=self.doc_a, clinic=self.clinic_a)
        self.assertEqual(link.commission_value, Decimal("25.00"))
        self.assertIsNotNone(link.commission_updated_at)

    def test_patch_fee_syncs_upcoming_expected_not_paid_received(self):
        upcoming = make_appointment(
            patient=self.patient,
            doctor=self.doc_a,
            clinic=self.clinic_a,
            scheduled_at=_slot(2, 11),
            token_number=2,
            status=Appointment.Status.UPCOMING,
        )
        upcoming.payment_status = Appointment.PaymentStatus.PENDING
        upcoming.payment_amount_expected = Decimal("2000.00")
        upcoming.save(
            update_fields=["payment_status", "payment_amount_expected"]
        )
        paid_received = self.appt.payment_amount_received

        self.client.force_authenticate(user=self.admin_a)
        res = self.client.patch(
            f"/api/clinic/doctors/{self.doc_a.uuid}/",
            {
                "consultation_fee": "1000.00",
                "commission_type": "percentage",
                "commission_value": "50.00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["consultation_fee"], "1000.00")

        upcoming.refresh_from_db()
        self.appt.refresh_from_db()
        self.assertEqual(upcoming.payment_amount_expected, Decimal("1000.00"))
        self.assertEqual(self.appt.payment_amount_received, paid_received)

        # Completed paid row keeps received fee base; new % applies.
        completed = next(
            a for a in res.data["appointments"] if a["id"] == self.appt.id
        )
        self.assertEqual(completed["fee_base"], "2000.00")
        self.assertEqual(completed["clinic_share"], "1000.00")
        self.assertEqual(completed["doctor_share"], "1000.00")

        # Upcoming uses synced expected fee + new %.
        upcoming_row = next(
            a for a in res.data["appointments"] if a["id"] == upcoming.id
        )
        self.assertEqual(upcoming_row["fee_base"], "1000.00")
        self.assertEqual(upcoming_row["clinic_share"], "500.00")
        self.assertEqual(upcoming_row["doctor_share"], "500.00")
