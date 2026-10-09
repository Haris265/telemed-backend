import json
from datetime import date, timedelta

from django.test import TestCase

from appointments.services import book_token, pakistan_today
from assistant.context import ClinicContext
from assistant.services.cancellation import cancel_for_patient
from assistant.services.patients import get_or_create_patient
from assistant.tests import factories as f
from assistant.tools import build_tools
from assistant.tools.booking import FEE_LABEL, PAYMENT_CASH


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

    def _future_open(self):
        from assistant.services import slots as slot_svc

        dates = slot_svc.next_available_dates(self.doctor, self.clinic, limit=5)
        today = pakistan_today()
        chosen = next(
            row for row in dates if date.fromisoformat(row["date"]) > today
        )
        times = slot_svc.open_times_for_date(
            self.doctor, self.clinic, date.fromisoformat(chosen["date"])
        )
        self.assertGreaterEqual(len(times), 2)
        return chosen, times

    def test_prepare_blocks_existing_active_appointment(self):
        chosen, times = self._future_open()
        patient = f.make_patient(self.ctx.phone, name="Sara Ali")
        book_token(
            patient,
            self.doctor,
            date.fromisoformat(chosen["date"]) + timedelta(days=1),
            slot_time=__import__("datetime").time(11, 0),
            clinic=self.clinic,
        )
        tools = self._tools()
        prep = json.loads(
            tools["prepare_booking"].invoke(
                {
                    "doctor_id": self.doctor.id,
                    "token_date": chosen["date"],
                    "slot_time": times[0]["time"],
                }
            )
        )
        self.assertFalse(prep["ok"])
        self.assertEqual(prep["error"]["code"], "active_appointment_exists")
        facts = prep["error"]["appointment"]
        for key in ("token_code", "doctor", "date_label", "time_label", "can_cancel", "cancel_until"):
            self.assertIn(key, facts)
        self.assertIsNone(self.session["pending"])

    def test_confirm_blocks_appointment_created_after_prepare(self):
        from assistant.services import slots as slot_svc

        chosen, times = self._future_open()
        tools = self._tools()
        prep = json.loads(
            tools["prepare_booking"].invoke(
                {
                    "doctor_id": self.doctor.id,
                    "token_date": chosen["date"],
                    "slot_time": times[0]["time"],
                }
            )
        )
        self.assertTrue(prep["ok"], prep)
        patient = get_or_create_patient(phone=self.ctx.phone, name="Sara Ali")
        book_token(
            patient,
            self.doctor,
            date.fromisoformat(chosen["date"]),
            slot_time=slot_svc.parse_slot_time(times[1]["time"]),
            clinic=self.clinic,
        )
        self.session["turn_no"] = 2
        self.session["patient_name"] = "Sara Ali"
        confirm = json.loads(tools["confirm_booking"].invoke({}))
        self.assertFalse(confirm["ok"])
        self.assertEqual(confirm["error"]["code"], "active_appointment_exists")
        self.assertIn("token_code", confirm["error"]["appointment"])
        self.assertIsNone(self.session["pending"])

    def test_cancel_then_prepare_and_confirm(self):
        chosen, times = self._future_open()
        patient = f.make_patient(self.ctx.phone, name="Sara Ali")
        existing = book_token(
            patient,
            self.doctor,
            date.fromisoformat(chosen["date"]) + timedelta(days=1),
            slot_time=__import__("datetime").time(11, 0),
            clinic=self.clinic,
        )
        tools = self._tools()
        blocked = json.loads(
            tools["prepare_booking"].invoke(
                {
                    "doctor_id": self.doctor.id,
                    "token_date": chosen["date"],
                    "slot_time": times[0]["time"],
                }
            )
        )
        self.assertEqual(blocked["error"]["code"], "active_appointment_exists")
        cancel_for_patient(existing.id, patient=patient, clinic=self.clinic)
        prep = json.loads(
            tools["prepare_booking"].invoke(
                {
                    "doctor_id": self.doctor.id,
                    "token_date": chosen["date"],
                    "slot_time": times[0]["time"],
                }
            )
        )
        self.assertTrue(prep["ok"], prep)
        self.session["turn_no"] = 2
        json.loads(tools["set_patient_name"].invoke({"name": "Sara Ali"}))
        confirm = json.loads(tools["confirm_booking"].invoke({}))
        self.assertTrue(confirm["ok"], confirm)

    def test_prepare_and_confirm_share_fee_fields(self):
        chosen, times = self._future_open()
        tools = self._tools()
        prep = json.loads(
            tools["prepare_booking"].invoke(
                {
                    "doctor_id": self.doctor.id,
                    "token_date": chosen["date"],
                    "slot_time": times[0]["time"],
                }
            )
        )
        self.assertTrue(prep["ok"], prep)
        summary = prep["data"]["confirm_summary"]
        self.session["turn_no"] = 2
        json.loads(tools["set_patient_name"].invoke({"name": "Sara Ali"}))
        confirm = json.loads(tools["confirm_booking"].invoke({}))
        self.assertTrue(confirm["ok"], confirm)
        for key in ("clinic", "payment", "fee", "fee_label"):
            self.assertEqual(summary[key], confirm["data"][key])
        self.assertEqual(summary["payment"], PAYMENT_CASH)
        self.assertEqual(summary["fee_label"], FEE_LABEL)
        self.assertEqual(summary["clinic"], self.clinic.name)
