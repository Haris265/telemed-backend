import json

from django.test import TestCase

from assistant.context import ClinicContext
from assistant.tests import factories as f
from assistant.tools import build_tools


class BookingToolTests(TestCase):
    def setUp(self):
        self.clinic = f.make_clinic()
        self.spec = f.make_speciality("Dermatology")
        self.doctor = f.make_doctor(
            username="book_doc", clinic=self.clinic, specialities=[self.spec]
        )
        f.seed_week_availability(self.doctor, self.clinic)
        self.config = f.enable_assistant(self.clinic)
        self.session = {
            "turn_no": 1,
            "patient_name": "",
            "pending": None,
            "refs": [],
            "messages": [],
            "summary": "",
        }
        self.ctx = ClinicContext(
            clinic=self.clinic,
            config=self.config,
            plan=self.config.plan,
            phone="923007777777",
        )

    def _tools(self):
        return {t.name: t for t in build_tools(self.ctx, self.session)}

    def test_two_phase_same_turn_rejected(self):
        tools = self._tools()
        from assistant.services import slots as slot_svc

        dates = slot_svc.next_available_dates(self.doctor, self.clinic, limit=1)
        self.assertTrue(dates)
        times = slot_svc.open_times_for_date(
            self.doctor,
            self.clinic,
            __import__("datetime").date.fromisoformat(dates[0]["date"]),
        )
        self.assertTrue(times)
        prep = json.loads(
            tools["prepare_booking"].invoke(
                {
                    "doctor_id": self.doctor.id,
                    "token_date": dates[0]["date"],
                    "slot_time": times[0]["time"],
                }
            )
        )
        self.assertTrue(prep["ok"])
        # Same turn_no as prepare
        confirm = json.loads(tools["confirm_booking"].invoke({}))
        self.assertFalse(confirm["ok"])
        self.assertEqual(confirm["error"]["code"], "pending_not_confirmed")

    def test_confirm_next_turn_needs_name_then_books(self):
        tools = self._tools()
        from assistant.services import slots as slot_svc
        from datetime import date

        dates = slot_svc.next_available_dates(self.doctor, self.clinic, limit=1)
        times = slot_svc.open_times_for_date(
            self.doctor, self.clinic, date.fromisoformat(dates[0]["date"])
        )
        json.loads(
            tools["prepare_booking"].invoke(
                {
                    "doctor_id": self.doctor.id,
                    "token_date": dates[0]["date"],
                    "slot_time": times[0]["time"],
                }
            )
        )
        self.session["turn_no"] = 2
        confirm = json.loads(tools["confirm_booking"].invoke({}))
        self.assertEqual(confirm["error"]["code"], "needs_name")
        json.loads(tools["set_patient_name"].invoke({"name": "Sara Ali"}))
        confirm2 = json.loads(tools["confirm_booking"].invoke({}))
        self.assertTrue(confirm2["ok"], confirm2)
        self.assertIn("token_code", confirm2["data"])
