"""Playground HTML + JSON API (DEBUG + ASSISTANT_PLAYGROUND_ENABLED only)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant import settings_access as sa
from assistant.channels import playground as playground_channel
from assistant.guards import get_trace
from assistant.phone import canonical_phone
from assistant.redis_client import AssistantRedisUnavailable


def _playground_allowed() -> bool:
    return bool(settings.DEBUG) and sa.playground_enabled()


class PlaygroundGateMixin:
    authentication_classes = []
    permission_classes = [AllowAny]

    def dispatch(self, request, *args, **kwargs):
        if not _playground_allowed():
            return JsonResponse({"detail": "Playground disabled."}, status=404)
        return super().dispatch(request, *args, **kwargs)


class PlaygroundPageView(PlaygroundGateMixin, APIView):
    def get(self, request):
        clinic_id = request.GET.get("clinic_id", "")
        return render(
            request,
            "assistant/playground.html",
            {
                "clinic_id": clinic_id,
                "chat_url": reverse("assistant:chat"),
                "reset_url": reverse("assistant:reset"),
                "trace_enabled": sa.trace_enabled(),
            },
        )


class PlaygroundChatView(PlaygroundGateMixin, APIView):
    def post(self, request):
        data = request.data or {}
        try:
            clinic_id = int(data.get("clinic_id"))
        except (TypeError, ValueError):
            return Response({"detail": "clinic_id is required."}, status=400)
        phone = canonical_phone(str(data.get("phone") or ""))
        if len(phone) < 10:
            return Response({"detail": "Valid phone is required."}, status=400)
        message = str(data.get("message") or "").strip()
        if not message:
            return Response({"detail": "message is required."}, status=400)
        message_id = str(data.get("message_id") or uuid.uuid4())
        message_type = str(data.get("message_type") or "text")
        name = str(data.get("name") or "")

        try:
            result = playground_channel.handle_chat(
                clinic_id=clinic_id,
                phone=phone,
                message=message,
                message_id=message_id,
                message_type=message_type,
                name=name,
            )
            body = {
                "reply": result.reply,
                "session_id": result.session_id,
                "quota": result.quota,
                "outcome": result.outcome,
            }
            if result.notice:
                body["notice"] = result.notice
            if sa.trace_enabled():
                body["trace"] = get_trace(clinic_id, phone)
        except AssistantRedisUnavailable:
            return Response({"detail": "Redis unavailable."}, status=503)

        return Response(body, status=result.status)


class PlaygroundResetView(PlaygroundGateMixin, APIView):
    def post(self, request):
        data = request.data or {}
        try:
            clinic_id = int(data.get("clinic_id"))
        except (TypeError, ValueError):
            return Response({"detail": "clinic_id is required."}, status=400)
        phone = canonical_phone(str(data.get("phone") or ""))
        if len(phone) < 10:
            return Response({"detail": "Valid phone is required."}, status=400)
        try:
            result = playground_channel.handle_reset(clinic_id=clinic_id, phone=phone)
        except AssistantRedisUnavailable:
            return Response({"detail": "Redis unavailable."}, status=503)
        return Response(result)
