import hashlib
import hmac
import logging
import uuid
from typing import Any

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .fsm import handle_inbound_message
from .meta_client import MetaWhatsAppClient

logger = logging.getLogger(__name__)


def _verify_signature(request) -> bool:
    app_secret = settings.META_WA_APP_SECRET
    if not app_secret:
        # Allow local/dev without secret configured
        return True
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode("utf-8"),
        msg=request.body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature[7:], expected)


def _contacts_by_wa_id(value: dict[str, Any]) -> dict[str, str]:
    """Map WhatsApp id → display name from Meta contacts payload."""
    out: dict[str, str] = {}
    for contact in value.get("contacts", []) or []:
        wa_id = str(contact.get("wa_id") or "").strip()
        name = ((contact.get("profile") or {}).get("name") or "").strip()
        if wa_id and name:
            out[wa_id] = name
    return out


def _extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = _contacts_by_wa_id(value)
            for msg in value.get("messages", []) or []:
                # Attach WhatsApp profile name so FSM can store PatientProfile.name
                from_id = str(msg.get("from") or "").strip()
                profile_name = names.get(from_id, "")
                if profile_name:
                    msg = {**msg, "profile_name": profile_name}
                messages.append(msg)
    return messages


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        # Meta sends hub.mode / hub.verify_token; some proxies also send hub_mode.
        qp = request.query_params
        mode = (qp.get("hub.mode") or qp.get("hub_mode") or "").strip()
        token = (qp.get("hub.verify_token") or qp.get("hub_verify_token") or "").strip()
        challenge = qp.get("hub.challenge") or qp.get("hub_challenge") or ""
        expected = (settings.META_WA_VERIFY_TOKEN or "").strip()
        if mode == "subscribe" and expected and token == expected:
            return HttpResponse(str(challenge), content_type="text/plain")
        logger.warning(
            "WhatsApp webhook verify failed (mode=%r token_match=%s)",
            mode,
            bool(token) and token == expected,
        )
        return HttpResponseForbidden("Verification failed")

    def post(self, request):
        if not _verify_signature(request):
            return HttpResponseForbidden("Invalid signature")

        payload = request.data if isinstance(request.data, dict) else {}
        client = MetaWhatsAppClient()
        for msg in _extract_messages(payload):
            try:
                handle_inbound_message(msg, client)
            except Exception:
                logger.exception("Failed handling WhatsApp message %s", msg.get("id"))
        return Response({"status": "ok"})


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppSimulateView(APIView):
    """DEBUG helper to drive the FSM without Meta Cloud API."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if not settings.DEBUG:
            return Response({"detail": "Not available"}, status=status.HTTP_403_FORBIDDEN)

        phone = str(request.data.get("phone", "")).strip()
        text = str(request.data.get("text", "")).strip()
        profile_name = str(request.data.get("profile_name", "")).strip()
        if not phone or not text:
            return Response(
                {"detail": "phone and text are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        replies: list[str] = []

        class CaptureClient:
            def send_text(self, to: str, body: str):
                replies.append(body)
                return {"to": to, "body": body}

        msg = {
            "id": f"sim-{uuid.uuid4().hex}",
            "from": phone,
            "type": "text",
            "text": {"body": text},
        }
        if profile_name:
            msg["profile_name"] = profile_name
        handle_inbound_message(msg, CaptureClient())
        return Response({"replies": replies})
