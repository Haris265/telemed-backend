from unittest.mock import patch

from django.test import TestCase
from langchain_core.messages import AIMessage

from assistant.context import InboundMessage
from assistant.engine import run_turn
from assistant.tests import factories as f
from assistant.tests.helpers import fake_redis_client
from assistant.tests.scripted_model import ScriptedChatModel


class EngineTests(TestCase):
    def setUp(self):
        self.clinic = f.make_clinic()
        f.enable_assistant(self.clinic)

    def test_simple_reply(self):
        model = ScriptedChatModel([AIMessage(content="Hello from clinic assistant")])
        with fake_redis_client():
            with patch("assistant.engine.get_chat_model", return_value=model):
                result = run_turn(
                    InboundMessage(
                        clinic_id=self.clinic.id,
                        phone="03001234567",
                        message_id="e1",
                        kind="text",
                        text="salam",
                    )
                )
        self.assertEqual(result.status, 200)
        self.assertIn("Hello", result.reply)

    def test_dedupe_drops_second(self):
        model = ScriptedChatModel(
            [
                AIMessage(content="first"),
                AIMessage(content="second"),
            ]
        )
        with fake_redis_client():
            with patch("assistant.engine.get_chat_model", return_value=model):
                first = run_turn(
                    InboundMessage(
                        clinic_id=self.clinic.id,
                        phone="03001234567",
                        message_id="same",
                        kind="text",
                        text="hi",
                    )
                )
                second = run_turn(
                    InboundMessage(
                        clinic_id=self.clinic.id,
                        phone="03001234567",
                        message_id="same",
                        kind="text",
                        text="hi",
                    )
                )
        self.assertEqual(first.outcome, "ok")
        self.assertEqual(second.outcome, "duplicate")

    def test_llm_error_refunds(self):
        class Boom(ScriptedChatModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                raise RuntimeError("provider down")

        with fake_redis_client():
            with patch("assistant.engine.get_chat_model", return_value=Boom([])):
                result = run_turn(
                    InboundMessage(
                        clinic_id=self.clinic.id,
                        phone="03001234567",
                        message_id="boom",
                        kind="text",
                        text="hi",
                    )
                )
        self.assertEqual(result.status, 503)
        self.assertEqual(result.outcome, "llm_error")
        self.assertEqual(result.quota["clinic_text_used_today"], 0)

    def test_llm_auth_error_message(self):
        class AuthBoom(ScriptedChatModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                raise RuntimeError(
                    "Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}"
                )

        with fake_redis_client():
            with patch("assistant.engine.get_chat_model", return_value=AuthBoom([])):
                result = run_turn(
                    InboundMessage(
                        clinic_id=self.clinic.id,
                        phone="03001234567",
                        message_id="auth-boom",
                        kind="text",
                        text="hi",
                    )
                )
        self.assertEqual(result.status, 503)
        self.assertEqual(result.outcome, "llm_auth_error")
        self.assertIn("CHATBOT_LLM_API_KEY", result.reply)
        self.assertEqual(result.quota["clinic_text_used_today"], 0)
