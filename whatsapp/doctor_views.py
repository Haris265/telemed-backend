"""Doctor-facing WhatsApp connect APIs (Meta Embedded Signup)."""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsDoctor
from catalog.models import DoctorProfile

from .models import DoctorWhatsAppAccount
from .oauth import (
    exchange_embedded_signup_code,
    fetch_phone_display,
    subscribe_waba_webhooks,
)

logger = logging.getLogger(__name__)

SIGNUP_STATE_SALT = "whatsapp.embedded-signup"
SIGNUP_STATE_MAX_AGE = 60 * 30  # 30 minutes


def _doctor(request) -> DoctorProfile:
    return request.user.doctor_profile


def _account_for(doctor: DoctorProfile) -> DoctorWhatsAppAccount | None:
    return DoctorWhatsAppAccount.objects.filter(doctor=doctor).first()


def _status_payload(account: DoctorWhatsAppAccount | None) -> dict:
    if not account:
        payload = {
            "connected": False,
            "status": DoctorWhatsAppAccount.Status.DISCONNECTED,
            "display_phone": "",
            "phone_number_id": "",
            "waba_id": "",
            "connected_at": None,
            "last_error": "",
        }
    else:
        payload = {
            "connected": account.is_connected,
            "status": account.status,
            "display_phone": account.display_phone,
            "phone_number_id": account.phone_number_id,
            "waba_id": account.waba_id,
            "connected_at": account.connected_at,
            "last_error": account.last_error,
        }
    payload["manual_connect_allowed"] = bool(settings.DEBUG)
    if settings.DEBUG:
        payload["manual_connect_defaults"] = {
            "access_token": settings.META_WA_TOKEN or "",
            "phone_number_id": settings.META_WA_PHONE_NUMBER_ID or "",
            "waba_id": settings.META_WA_WABA_ID or "",
            "display_phone": settings.CLINIC_WHATSAPP_NUMBER or "",
        }
    return payload


def _apply_connected_credentials(
    account: DoctorWhatsAppAccount,
    *,
    access_token: str,
    phone_number_id: str,
    waba_id: str,
    display_phone: str = "",
    expires_in=None,
) -> DoctorWhatsAppAccount:
    display = display_phone.strip() or fetch_phone_display(
        access_token, phone_number_id
    )
    subscribed = subscribe_waba_webhooks(access_token, waba_id)
    if not subscribed:
        logger.warning(
            "WABA %s subscribe returned false for doctor %s",
            waba_id,
            account.doctor_id,
        )

    account.waba_id = waba_id
    account.phone_number_id = phone_number_id
    account.display_phone = display
    account.set_access_token(access_token)
    account.status = DoctorWhatsAppAccount.Status.CONNECTED
    account.connected_at = timezone.now()
    account.last_error = ""
    if expires_in:
        try:
            account.token_expires_at = timezone.now() + timedelta(
                seconds=int(expires_in)
            )
        except (TypeError, ValueError):
            account.token_expires_at = None
    else:
        account.token_expires_at = None
    account.save()
    return account


def _phone_conflict(doctor: DoctorProfile, phone_number_id: str):
    return (
        DoctorWhatsAppAccount.objects.filter(phone_number_id=phone_number_id)
        .exclude(doctor=doctor)
        .first()
    )


def _make_state(doctor_id: int) -> str:
    return signing.dumps(
        {"doctor_id": doctor_id, "ts": timezone.now().timestamp()},
        salt=SIGNUP_STATE_SALT,
    )


def _parse_state(state: str) -> dict:
    return signing.loads(state, salt=SIGNUP_STATE_SALT, max_age=SIGNUP_STATE_MAX_AGE)


def _signup_base_url(request) -> str:
    configured = (settings.META_EMBEDDED_SIGNUP_REDIRECT_URI or "").strip()
    if configured:
        # Allow either full signup page URL or origin; append path if needed.
        if "embedded-signup" in configured:
            return configured.rstrip("?")
        return configured.rstrip("/") + "/api/whatsapp/embedded-signup/"
    return request.build_absolute_uri("/api/whatsapp/embedded-signup/")


class DoctorWhatsAppStatusView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        account = _account_for(_doctor(request))
        return Response(_status_payload(account))


class DoctorWhatsAppSessionView(APIView):
    permission_classes = [IsDoctor]

    def post(self, request):
        doctor = _doctor(request)
        app_id = settings.META_APP_ID
        config_id = settings.META_EMBEDDED_SIGNUP_CONFIG_ID
        if not app_id or not config_id:
            return Response(
                {
                    "detail": (
                        "WhatsApp Embedded Signup is not configured. "
                        "Set META_APP_ID and META_EMBEDDED_SIGNUP_CONFIG_ID."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        account, _ = DoctorWhatsAppAccount.objects.get_or_create(doctor=doctor)
        if account.status == DoctorWhatsAppAccount.Status.CONNECTED:
            # Allow re-connect / replace flow; mark pending while signup runs.
            pass
        account.status = DoctorWhatsAppAccount.Status.PENDING
        account.last_error = ""
        account.save(update_fields=["status", "last_error", "updated_at"])

        state = _make_state(doctor.id)
        base = _signup_base_url(request)
        sep = "&" if "?" in base else "?"
        signup_url = f"{base}{sep}{urlencode({'state': state})}"

        return Response(
            {
                "app_id": app_id,
                "config_id": config_id,
                "state": state,
                "signup_url": signup_url,
                "redirect_scheme": "opd-doctor://whatsapp-callback",
            }
        )


class DoctorWhatsAppConnectView(APIView):
    permission_classes = [IsDoctor]

    def post(self, request):
        doctor = _doctor(request)
        code = str(request.data.get("code") or "").strip()
        waba_id = str(request.data.get("waba_id") or "").strip()
        phone_number_id = str(request.data.get("phone_number_id") or "").strip()
        state = str(request.data.get("state") or "").strip()

        if not code or not waba_id or not phone_number_id or not state:
            return Response(
                {
                    "detail": "code, waba_id, phone_number_id and state are required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = _parse_state(state)
        except signing.BadSignature:
            return Response(
                {"detail": "Invalid or expired signup state"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if int(payload.get("doctor_id") or 0) != doctor.id:
            return Response(
                {"detail": "Signup state does not match this doctor"},
                status=status.HTTP_403_FORBIDDEN,
            )

        conflict = _phone_conflict(doctor, phone_number_id)
        if conflict and conflict.is_connected:
            return Response(
                {"detail": "This WhatsApp number is already linked to another doctor"},
                status=status.HTTP_409_CONFLICT,
            )

        account, _ = DoctorWhatsAppAccount.objects.get_or_create(doctor=doctor)

        try:
            token_data = exchange_embedded_signup_code(code)
            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in")
            _apply_connected_credentials(
                account,
                access_token=access_token,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
                expires_in=expires_in,
            )
        except ValueError as exc:
            account.status = DoctorWhatsAppAccount.Status.ERROR
            account.last_error = str(exc)[:1000]
            account.save(update_fields=["status", "last_error", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("WhatsApp connect failed for doctor %s", doctor.id)
            account.status = DoctorWhatsAppAccount.Status.ERROR
            account.last_error = str(exc)[:1000]
            account.save(update_fields=["status", "last_error", "updated_at"])
            return Response(
                {"detail": "Failed to connect WhatsApp"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(_status_payload(account))


class DoctorWhatsAppConnectManualView(APIView):
    """DEBUG-only: paste Meta Cloud API credentials without Embedded Signup."""

    permission_classes = [IsDoctor]

    def post(self, request):
        if not settings.DEBUG:
            return Response(
                {"detail": "Manual WhatsApp connect is only available in DEBUG."},
                status=status.HTTP_403_FORBIDDEN,
            )

        doctor = _doctor(request)
        access_token = str(request.data.get("access_token") or "").strip()
        waba_id = str(request.data.get("waba_id") or "").strip()
        phone_number_id = str(request.data.get("phone_number_id") or "").strip()
        display_phone = str(request.data.get("display_phone") or "").strip()

        if not access_token or not waba_id or not phone_number_id:
            return Response(
                {
                    "detail": "access_token, waba_id and phone_number_id are required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        conflict = _phone_conflict(doctor, phone_number_id)
        if conflict and conflict.is_connected:
            return Response(
                {"detail": "This WhatsApp number is already linked to another doctor"},
                status=status.HTTP_409_CONFLICT,
            )

        account, _ = DoctorWhatsAppAccount.objects.get_or_create(doctor=doctor)
        try:
            _apply_connected_credentials(
                account,
                access_token=access_token,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
                display_phone=display_phone,
            )
        except Exception as exc:
            logger.exception(
                "Manual WhatsApp connect failed for doctor %s", doctor.id
            )
            account.status = DoctorWhatsAppAccount.Status.ERROR
            account.last_error = str(exc)[:1000]
            account.save(update_fields=["status", "last_error", "updated_at"])
            return Response(
                {"detail": "Failed to connect WhatsApp"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(_status_payload(account))


class DoctorWhatsAppDisconnectView(APIView):
    permission_classes = [IsDoctor]

    def delete(self, request):
        doctor = _doctor(request)
        account = _account_for(doctor)
        if not account:
            return Response(_status_payload(None))

        account.status = DoctorWhatsAppAccount.Status.DISCONNECTED
        account.access_token_encrypted = ""
        account.phone_number_id = ""
        account.waba_id = ""
        account.display_phone = ""
        account.token_expires_at = None
        account.connected_at = None
        account.last_error = ""
        account.save()
        return Response(_status_payload(account))
