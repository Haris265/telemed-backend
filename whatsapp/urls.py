from django.urls import path

from .views import WhatsAppSimulateView, WhatsAppWebhookView

urlpatterns = [
    path("webhook/", WhatsAppWebhookView.as_view(), name="wa-webhook"),
    path("simulate/", WhatsAppSimulateView.as_view(), name="wa-simulate"),
]
