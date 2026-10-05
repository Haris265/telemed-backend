from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from appointments.services import (
    CancellationNotAllowed,
    can_cancel_appointment,
    cancel_appointment_by_patient,
    open_slot_options,
    pakistan_now,
    upcoming_available_dates,
)
from assistant.tests import factories as f


class SlotAndCancelDomainTests(TestCase):
    def setUp(self):
        self.clinic = f.make_clinic("Clinic A")
        self.spec = f.make_speciality("Cardiology")
        self.doctor = f.make_doctor(
            username="doc_a",
            clinic=self.clinic,
            specialities=[self.spec],
        )
        f.seed_week_availability(self.doctor, self.clinic)
        self.patient = f.make_patient("923001111111")

    def test_open_slot_options_excludes_booked(self):
        options = upcoming_available_dates(self.doctor, clinic=self.clinic, days_ahead=7, limit=1)
        self.assertTrue(options)
        option = options[0]
        open_before = open_slot_options(self.doctor, option)
        self.assertTrue(open_before)
        booked = open_before[0]["time"]
        option["booked_times"] = [booked]
        open_after = open_slot_options(self.doctor, option)
        self.assertTrue(all(s["time"] != booked for s in open_after))

    def test_upcoming_dates_bounded_by_days_ahead(self):
        # Should not raise and returns limited horizon.
        options = upcoming_available_dates(self.doctor, clinic=self.clinic, days_ahead=3, limit=10)
        today = pakistan_now().date()
        for opt in options:
            day = __import__("datetime").date.fromisoformat(opt["date"])
            self.assertLessEqual((day - today).days, 3)

    def test_cancel_boundaries(self):
        now = timezone.now()
        far = now + timedelta(minutes=61)
        exact = now + timedelta(minutes=60)
        near = now + timedelta(minutes=59, seconds=59)
        five = now + timedelta(minutes=5)

        for scheduled, expect_ok in ((far, True), (exact, True), (near, False), (five, False)):
            appt = f.make_appointment(
                patient=self.patient,
                doctor=self.doctor,
                clinic=self.clinic,
                scheduled_at=scheduled,
                token_number=int(scheduled.timestamp()) % 100000,
            )
            allowed, _ = can_cancel_appointment(appt, now=now)
            self.assertEqual(allowed, expect_ok, msg=str(scheduled))
            if expect_ok:
                cancel_appointment_by_patient(
                    appt.id, self.patient, self.clinic, now=now
                )
                appt.refresh_from_db()
                self.assertEqual(appt.status, "cancelled")
            else:
                with self.assertRaises(CancellationNotAllowed) as ctx:
                    cancel_appointment_by_patient(
                        appt.id, self.patient, self.clinic, now=now
                    )
                self.assertEqual(ctx.exception.code, "cancel_window_closed")

    def test_visit_started_blocks_cancel(self):
        now = timezone.now()
        appt = f.make_appointment(
            patient=self.patient,
            doctor=self.doctor,
            clinic=self.clinic,
            scheduled_at=now + timedelta(hours=3),
            token_number=9,
        )
        appt.visit_started_at = now
        appt.save(update_fields=["visit_started_at"])
        with self.assertRaises(CancellationNotAllowed) as ctx:
            cancel_appointment_by_patient(appt.id, self.patient, self.clinic, now=now)
        self.assertEqual(ctx.exception.code, "visit_already_started")

    def test_other_patient_not_found(self):
        now = timezone.now()
        other = f.make_patient("923009999999", name="Other")
        appt = f.make_appointment(
            patient=other,
            doctor=self.doctor,
            clinic=self.clinic,
            scheduled_at=now + timedelta(hours=3),
            token_number=11,
        )
        with self.assertRaises(CancellationNotAllowed) as ctx:
            cancel_appointment_by_patient(appt.id, self.patient, self.clinic, now=now)
        self.assertEqual(ctx.exception.code, "appointment_not_found")

    def test_rebook_after_cancel(self):
        from appointments.services import book_token
        from datetime import time

        now = timezone.now()
        day = (now + timedelta(days=1)).date()
        slot = time(10, 0)
        appt = book_token(
            self.patient,
            self.doctor,
            day,
            slot_time=slot,
            clinic=self.clinic,
        )
        # Move scheduled far enough and cancel
        appt.scheduled_at = now + timedelta(hours=5)
        appt.save(update_fields=["scheduled_at"])
        cancel_appointment_by_patient(appt.id, self.patient, self.clinic, now=now)
        again = book_token(
            self.patient,
            self.doctor,
            day,
            slot_time=slot,
            clinic=self.clinic,
        )
        self.assertEqual(again.status, "upcoming")
