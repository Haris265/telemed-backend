from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from assistant.tests import factories as f
from assistant.tests.helpers import fake_redis_client


@override_settings(DEBUG=True, ASSISTANT_PLAYGROUND_ENABLED=True)
class PlaygroundAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.clinic = f.make_clinic()
        f.enable_assistant(self.clinic)

    def test_gating_requires_flag(self):
        with override_settings(ASSISTANT_PLAYGROUND_ENABLED=False):
            res = self.client.get("/api/assistant/playground/")
            self.assertEqual(res.status_code, 404)

    def test_unknown_clinic_404(self):
        with fake_redis_client():
            res = self.client.post(
                "/api/assistant/chat/",
                {
                    "clinic_id": 999999,
                    "phone": "03001234567",
                    "message": "hello",
                    "message_id": "m1",
                },
                format="json",
            )
            self.assertEqual(res.status_code, 404)

    def test_disabled_clinic_403(self):
        self.clinic.assistant_config.is_enabled = False
        self.clinic.assistant_config.save()
        with fake_redis_client():
            res = self.client.post(
                "/api/assistant/chat/",
                {
                    "clinic_id": self.clinic.id,
                    "phone": "03001234567",
                    "message": "hello",
                    "message_id": "m2",
                },
                format="json",
            )
            self.assertEqual(res.status_code, 403)

    def test_validation_400(self):
        res = self.client.post("/api/assistant/chat/", {"clinic_id": self.clinic.id}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_chat_with_scripted_model(self):
        from langchain_core.messages import AIMessage
        from assistant.tests.scripted_model import ScriptedChatModel

        model = ScriptedChatModel([AIMessage(content="Assalam o alaikum, how can I help?")])
        with fake_redis_client():
            with patch("assistant.engine.get_chat_model", return_value=model):
                res = self.client.post(
                    "/api/assistant/chat/",
                    {
                        "clinic_id": self.clinic.id,
                        "phone": "03001234567",
                        "message": "hello",
                        "message_id": "m3",
                    },
                    format="json",
                )
        self.assertEqual(res.status_code, 200)
        self.assertIn("Assalam", res.data["reply"])
        self.assertIn("quota", res.data)
