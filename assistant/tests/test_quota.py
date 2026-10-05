from django.test import TestCase

from assistant import quota
from assistant.tests import factories as f
from assistant.tests.helpers import fake_redis_client


class QuotaTests(TestCase):
    def setUp(self):
        self.clinic = f.make_clinic()
        self.plan = f.ensure_plan("A")
        self.phone = "923001234567"

    def test_patient_cap_and_notice_once(self):
        with fake_redis_client():
            for _ in range(10):
                quota.count_patient_reply(self.clinic.id, self.phone)
            self.assertTrue(quota.patient_at_cap(self.clinic.id, self.phone, self.plan))
            self.assertTrue(quota.claim_patient_notice(self.clinic.id, self.phone))
            self.assertFalse(quota.claim_patient_notice(self.clinic.id, self.phone))

    def test_day_reserve_and_refund(self):
        with fake_redis_client():
            tiny = f.ensure_plan("A")
            tiny.max_text_messages_per_day = 2
            tiny.save()
            self.assertTrue(quota.reserve_day_slot(self.clinic.id, "text", tiny))
            self.assertTrue(quota.reserve_day_slot(self.clinic.id, "text", tiny))
            self.assertFalse(quota.reserve_day_slot(self.clinic.id, "text", tiny))
            quota.refund_day_slot(self.clinic.id, "text")
            self.assertTrue(quota.reserve_day_slot(self.clinic.id, "text", tiny))

    def test_patient_first_ordering_does_not_need_day_slot(self):
        with fake_redis_client():
            for _ in range(10):
                quota.count_patient_reply(self.clinic.id, self.phone)
            self.assertTrue(quota.patient_at_cap(self.clinic.id, self.phone, self.plan))
            # Day counter untouched when patient blocked before reserve.
            snap = quota.snapshot(self.clinic.id, self.phone, self.plan)
            self.assertEqual(snap.clinic_text_used_today, 0)
