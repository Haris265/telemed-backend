from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from assistant.llm import get_chat_model


class LlmFactoryTests(SimpleTestCase):
    @override_settings(
        CHATBOT_LLM_PROVIDER="openrouter",
        CHATBOT_LLM_API_KEY="k",
        CHATBOT_LLM_MODEL="deepseek/deepseek-v4.1-flash",
        CHATBOT_LLM_BASE_URL="https://openrouter.ai/api/v1",
    )
    def test_openrouter(self):
        model = get_chat_model()
        self.assertEqual(model.model_name, "deepseek/deepseek-v4.1-flash")

    @override_settings(CHATBOT_LLM_PROVIDER="nope")
    def test_unknown_provider(self):
        with self.assertRaises(ImproperlyConfigured):
            get_chat_model()
