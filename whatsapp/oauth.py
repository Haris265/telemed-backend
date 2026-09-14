"""Meta Graph helpers for Embedded Signup code exchange and WABA subscribe."""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def graph_base() -> str:
    version = getattr(settings, "META_GRAPH_VERSION", "v21.0") or "v21.0"
    return f"https://graph.facebook.com/{version}"


def exchange_embedded_signup_code(code: str) -> dict[str, Any]:
    """Exchange Embedded Signup authorization code for a user access token."""
    app_id = settings.META_APP_ID
    app_secret = settings.META_APP_SECRET or settings.META_WA_APP_SECRET
    if not app_id or not app_secret:
        raise ValueError("META_APP_ID and META_APP_SECRET are required")
    if not code:
        raise ValueError("authorization code is required")

    url = f"{graph_base()}/oauth/access_token"
    resp = requests.get(
        url,
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
        },
        timeout=30,
    )
    if not resp.ok:
        logger.error(
            "Meta code exchange failed (%s): %s",
            resp.status_code,
            resp.text[:800],
        )
        raise ValueError(f"Meta code exchange failed: {resp.text[:300]}")
    data = resp.json() or {}
    if not data.get("access_token"):
        raise ValueError("Meta code exchange returned no access_token")
    return data


def fetch_phone_display(token: str, phone_number_id: str) -> str:
    if not token or not phone_number_id:
        return ""
    url = f"{graph_base()}/{phone_number_id}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "display_phone_number,verified_name"},
            timeout=20,
        )
        if not resp.ok:
            logger.error(
                "Phone display lookup failed (%s): %s",
                resp.status_code,
                resp.text[:500],
            )
            return ""
        display = (resp.json() or {}).get("display_phone_number") or ""
        return "".join(ch for ch in display if ch.isdigit()) or display.strip()
    except Exception:
        logger.exception("Failed fetching phone display for %s", phone_number_id)
        return ""


def subscribe_waba_webhooks(token: str, waba_id: str) -> bool:
    """Subscribe this Meta app to the WABA so webhooks are delivered."""
    if not token or not waba_id:
        return False
    url = f"{graph_base()}/{waba_id}/subscribed_apps"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if not resp.ok:
            logger.error(
                "WABA subscribe failed (%s) waba=%s: %s",
                resp.status_code,
                waba_id,
                resp.text[:500],
            )
            return False
        return bool((resp.json() or {}).get("success", True))
    except Exception:
        logger.exception("Failed subscribing WABA %s", waba_id)
        return False
