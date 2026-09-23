import hashlib
import hmac
import logging
import uuid
from typing import Any

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .fsm import handle_inbound_message
from .meta_client import MetaWhatsAppClient
from .models import DoctorWhatsAppAccount

logger = logging.getLogger(__name__)


def _verify_signature(request) -> bool:
    app_secret = settings.META_WA_APP_SECRET or settings.META_APP_SECRET
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


def _extract_message_batches(
    payload: dict[str, Any],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Return list of (phone_number_id, messages) from a Meta webhook payload."""
    batches: list[tuple[str, list[dict[str, Any]]]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            names = _contacts_by_wa_id(value)
            messages: list[dict[str, Any]] = []
            for msg in value.get("messages", []) or []:
                from_id = str(msg.get("from") or "").strip()
                profile_name = names.get(from_id, "")
                if profile_name:
                    msg = {**msg, "profile_name": profile_name}
                messages.append(msg)
            if messages:
                batches.append((phone_number_id, messages))
    return batches


def _resolve_client_and_doctor(
    phone_number_id: str,
) -> tuple[MetaWhatsAppClient, DoctorWhatsAppAccount | None]:
    """Resolve outbound client + optional bound doctor for an inbound Meta number.

    If any doctor CONNECTED their WhatsApp to this Meta phone_number_id
    (including the shared test/platform number via manual connect), the bot
    runs for that doctor only. Otherwise use platform credentials and the
    marketplace specialty → doctor flow.
    """
    phone_number_id = (phone_number_id or "").strip()
    if phone_number_id:
        account = (
            DoctorWhatsAppAccount.objects.select_related("doctor")
            .filter(
                phone_number_id=phone_number_id,
                status=DoctorWhatsAppAccount.Status.CONNECTED,
            )
            .first()
        )
        if account and account.is_connected:
            client = MetaWhatsAppClient(
                token=account.get_access_token(),
                phone_number_id=account.phone_number_id,
            )
            return client, account

    return MetaWhatsAppClient.platform(), None


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
        for phone_number_id, messages in _extract_message_batches(payload):
            client, account = _resolve_client_and_doctor(phone_number_id)
            bound_doctor = account.doctor if account else None
            for msg in messages:
                try:
                    handle_inbound_message(msg, client, doctor=bound_doctor)
                except Exception:
                    logger.exception(
                        "Failed handling WhatsApp message %s", msg.get("id")
                    )
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
        image_id = str(request.data.get("image_id", "")).strip()
        doctor_id = request.data.get("doctor_id")
        if not phone or (not text and not image_id):
            return Response(
                {"detail": "phone and text (or image_id) are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        replies: list[str] = []

        class CaptureClient:
            def send_text(self, to: str, body: str):
                replies.append(body)
                return {"to": to, "body": body}

            def download_media(self, media_id: str):
                # DEBUG: accept raw base64 slip via request for OCR testing
                import base64

                b64 = str(request.data.get("image_base64", "")).strip()
                mime = str(request.data.get("image_mime", "image/jpeg")).strip()
                if not b64:
                    return None
                try:
                    return base64.b64decode(b64), mime
                except Exception:
                    return None

        msg: dict[str, Any] = {
            "id": f"sim-{uuid.uuid4().hex}",
            "from": phone,
            "type": "image" if image_id and not text else "text",
            "text": {"body": text},
        }
        if image_id:
            msg["type"] = "image"
            msg["image"] = {"id": image_id, "caption": text}
        if profile_name:
            msg["profile_name"] = profile_name

        # doctor_id mirrors a linked / Meta-testing WhatsApp number for that doctor.
        bound_doctor = None
        if doctor_id is not None and str(doctor_id).strip() != "":
            from catalog.models import DoctorProfile

            try:
                did = int(doctor_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "doctor_id must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            bound_doctor = DoctorProfile.objects.filter(id=did, is_active=True).first()
            if not bound_doctor:
                return Response(
                    {"detail": "doctor_id not found or inactive"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        handle_inbound_message(msg, CaptureClient(), doctor=bound_doctor)
        return Response(
            {
                "replies": replies,
                "bound_doctor_id": bound_doctor.id if bound_doctor else None,
            }
        )


class EmbeddedSignupPageView(View):
    """Host page that runs Meta Embedded Signup and deep-links back to the app."""

    def get(self, request):
        state = (request.GET.get("state") or "").strip()
        app_id = settings.META_APP_ID
        config_id = settings.META_EMBEDDED_SIGNUP_CONFIG_ID
        if not app_id or not config_id:
            return HttpResponse(
                "WhatsApp Embedded Signup is not configured on the server.",
                status=503,
                content_type="text/plain",
            )
        if not state:
            return HttpResponse(
                "Missing state parameter.",
                status=400,
                content_type="text/plain",
            )
        redirect_uri = (request.GET.get("redirect_uri") or "").strip()
        if not redirect_uri:
            redirect_uri = (
                getattr(settings, "DOCTOR_WEB_WHATSAPP_REDIRECT_URI", "") or ""
            ).strip()
        if not redirect_uri:
            redirect_uri = "opd-doctor://whatsapp-callback"
        return render(
            request,
            "whatsapp/embedded_signup.html",
            {
                "app_id": app_id,
                "config_id": config_id,
                "state": state,
                "redirect_scheme": redirect_uri,
            },
        )
