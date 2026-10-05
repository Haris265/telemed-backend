import json

from django.test import TestCase

from assistant.context import ClinicContext
from assistant.tests import factories as f
from assistant.tools import build_tools


class TenancyToolTests(TestCase):
    def setUp(self):
        self.clinic_a = f.make_clinic("Clinic A")
        self.clinic_b = f.make_clinic("Clinic B")
        self.spec = f.make_speciality("Cardiology")
        self.doc_a = f.make_doctor(
            username="ten_a", clinic=self.clinic_a, specialities=[self.spec], first_name="A"
        )
        self.doc_b = f.make_doctor(
            username="ten_b", clinic=self.clinic_b, specialities=[self.spec], first_name="B"
        )
        f.seed_week_availability(self.doc_a, self.clinic_a)
        f.seed_week_availability(self.doc_b, self.clinic_b)
        self.config = f.enable_assistant(self.clinic_a)
        self.ctx = ClinicContext(
            clinic=self.clinic_a,
            config=self.config,
            plan=self.config.plan,
            phone="923001234567",
        )
        self.session = {
            "turn_no": 1,
            "patient_name": "Ali",
            "pending": None,
            "refs": [],
            "messages": [],
            "summary": "",
        }

    def _tool(self, name: str):
        tools = {t.name: t for t in build_tools(self.ctx, self.session)}
        return tools[name]

    def test_other_clinic_doctor_rejected(self):
        result = json.loads(self._tool("get_doctor_availability").invoke({"doctor_id": self.doc_b.id}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "not_in_clinic")

    def test_overview_only_this_clinic(self):
        result = json.loads(
            self._tool("get_speciality_overview").invoke({"speciality_id": self.spec.id})
        )
        self.assertTrue(result["ok"])
        ids = {d["doctor_id"] for d in result["data"]["doctors"]}
        self.assertIn(self.doc_a.id, ids)
        self.assertNotIn(self.doc_b.id, ids)

    def test_legacy_fk_only_doctor_not_served(self):
        # Doctor linked only via legacy FK, not DoctorClinic
        from catalog.models import DoctorClinic
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(username="legacy", email="l@e.com", password="x", role="doctor")
        from catalog.models import DoctorProfile
        from decimal import Decimal

        legacy = DoctorProfile.objects.create(
            user=user,
            first_name="Legacy",
            last_name="Doc",
            clinic=self.clinic_a,
            consultation_fee=Decimal("1000"),
            is_active=True,
        )
        DoctorClinic.objects.filter(doctor=legacy).delete()
        result = json.loads(self._tool("get_doctor_availability").invoke({"doctor_id": legacy.id}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "not_in_clinic")
