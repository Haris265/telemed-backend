"""LangChain chat model factory — the only provider-aware module."""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from . import settings_access as sa


def get_chat_model() -> BaseChatModel:
    """Return the configured chat model. This is the only provider-aware code."""
    provider = sa.llm_provider()
    if provider in ("openrouter", "openai", "openai_compatible"):
        kwargs: dict = {
            "model": sa.llm_model(),
            "api_key": sa.llm_api_key() or "missing-key",
            "base_url": sa.llm_base_url(),
            "temperature": sa.llm_temperature(),
            "timeout": sa.llm_timeout_seconds(),
            "max_retries": sa.llm_max_retries(),
        }
        if provider == "openrouter":
            # OpenRouter recommends identifying the client app.
            kwargs["default_headers"] = {
                "HTTP-Referer": "https://telemed.local",
                "X-Title": "Telemed Clinic Assistant",
            }
        return ChatOpenAI(**kwargs)
    raise ImproperlyConfigured(f"Unsupported CHATBOT_LLM_PROVIDER={provider!r}")
