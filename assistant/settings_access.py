"""Typed accessors for assistant-related Django settings with defaults."""

from __future__ import annotations

from django.conf import settings


def _int(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def _float(name: str, default: float) -> float:
    return float(getattr(settings, name, default))


def _str(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or default)


def _bool(name: str, default: bool = False) -> bool:
    return bool(getattr(settings, name, default))


def redis_url() -> str:
    return _str("ASSISTANT_REDIS_URL", "redis://127.0.0.1:6379/1")


def session_ttl_seconds() -> int:
    return _int("ASSISTANT_SESSION_TTL_SECONDS", 604800)


def max_session_messages() -> int:
    return _int("ASSISTANT_MAX_SESSION_MESSAGES", 15)


def keep_after_compact() -> int:
    return _int("ASSISTANT_KEEP_AFTER_COMPACT", 6)


def summary_max_chars() -> int:
    return _int("ASSISTANT_SUMMARY_MAX_CHARS", 1500)


def max_tool_rounds() -> int:
    return _int("ASSISTANT_MAX_TOOL_ROUNDS", 6)


def turn_time_budget_seconds() -> float:
    return _float("ASSISTANT_TURN_TIME_BUDGET_SECONDS", 45.0)


def tool_result_max_chars() -> int:
    return _int("ASSISTANT_TOOL_RESULT_MAX_CHARS", 4000)


def reply_max_chars() -> int:
    return _int("ASSISTANT_REPLY_MAX_CHARS", 1800)


def max_doctors_per_overview() -> int:
    return _int("ASSISTANT_MAX_DOCTORS_PER_OVERVIEW", 5)


def overview_dates() -> int:
    return _int("ASSISTANT_OVERVIEW_DATES", 2)


def overview_slots_per_date() -> int:
    return _int("ASSISTANT_OVERVIEW_SLOTS_PER_DATE", 3)


def rate_limit_per_minute() -> int:
    return _int("ASSISTANT_RATE_LIMIT_PER_MINUTE", 8)


def trace_enabled() -> bool:
    return _bool("ASSISTANT_TRACE_ENABLED", False)


def playground_enabled() -> bool:
    return _bool("ASSISTANT_PLAYGROUND_ENABLED", False)


def cancel_min_lead_minutes() -> int:
    return _int("ASSISTANT_CANCEL_MIN_LEAD_MINUTES", 60)


def llm_provider() -> str:
    return _str("CHATBOT_LLM_PROVIDER", "openrouter")


def llm_api_key() -> str:
    return _str("CHATBOT_LLM_API_KEY", "")


def llm_model() -> str:
    return _str("CHATBOT_LLM_MODEL", "deepseek/deepseek-v4.1-flash")


def llm_base_url() -> str:
    return _str("CHATBOT_LLM_BASE_URL", "https://openrouter.ai/api/v1")


def llm_temperature() -> float:
    return _float("CHATBOT_LLM_TEMPERATURE", 0.3)


def llm_timeout_seconds() -> float:
    return _float("CHATBOT_LLM_TIMEOUT_SECONDS", 30.0)


def llm_max_retries() -> int:
    return _int("CHATBOT_LLM_MAX_RETRIES", 2)


def message_content_max_chars() -> int:
    return _int("ASSISTANT_MESSAGE_CONTENT_MAX_CHARS", 2000)


def user_input_max_chars() -> int:
    return _int("ASSISTANT_USER_INPUT_MAX_CHARS", 1000)


def max_session_turns() -> int:
    return _int("ASSISTANT_MAX_SESSION_TURNS", 300)


KEY_PREFIX = "asst:v1:"
