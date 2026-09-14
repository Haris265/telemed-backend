from django.urls import path

from .doctor_views import (
    DoctorWhatsAppConnectManualView,
    DoctorWhatsAppConnectView,
    DoctorWhatsAppDisconnectView,
    DoctorWhatsAppSessionView,
    DoctorWhatsAppStatusView,
)
from .views import EmbeddedSignupPageView, WhatsAppSimulateView, WhatsAppWebhookView

urlpatterns = [
    path("webhook/", WhatsAppWebhookView.as_view(), name="wa-webhook"),
    path("simulate/", WhatsAppSimulateView.as_view(), name="wa-simulate"),
    path(
        "embedded-signup/",
        EmbeddedSignupPageView.as_view(),
        name="wa-embedded-signup",
    ),
]

doctor_whatsapp_urlpatterns = [
    path(
        "whatsapp/status/",
        DoctorWhatsAppStatusView.as_view(),
        name="doctor-whatsapp-status",
    ),
    path(
        "whatsapp/session/",
        DoctorWhatsAppSessionView.as_view(),
        name="doctor-whatsapp-session",
    ),
    path(
        "whatsapp/connect/",
        DoctorWhatsAppConnectView.as_view(),
        name="doctor-whatsapp-connect",
    ),
    path(
        "whatsapp/connect-manual/",
        DoctorWhatsAppConnectManualView.as_view(),
        name="doctor-whatsapp-connect-manual",
    ),
    path(
        "whatsapp/disconnect/",
        DoctorWhatsAppDisconnectView.as_view(),
        name="doctor-whatsapp-disconnect",
    ),
]
