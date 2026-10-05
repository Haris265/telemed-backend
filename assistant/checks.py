from django.core.checks import Warning, register


@register()
def check_assistant_fernet_key(app_configs, **kwargs):
    from django.conf import settings

    errors = []
    key = (getattr(settings, "META_TOKEN_FERNET_KEY", "") or "").strip()
    if not key and not settings.DEBUG:
        errors.append(
            Warning(
                "META_TOKEN_FERNET_KEY is unset outside DEBUG; "
                "assistant secrets fall back to SECRET_KEY derivation.",
                id="assistant.W001",
            )
        )
    return errors


@register()
def check_assistant_redis_url(app_configs, **kwargs):
    from django.conf import settings

    errors = []
    playground = bool(getattr(settings, "ASSISTANT_PLAYGROUND_ENABLED", False))
    url = (getattr(settings, "ASSISTANT_REDIS_URL", "") or "").strip()
    if playground and not url:
        errors.append(
            Warning(
                "ASSISTANT_REDIS_URL is unset while ASSISTANT_PLAYGROUND_ENABLED is on.",
                id="assistant.W002",
            )
        )
    return errors
