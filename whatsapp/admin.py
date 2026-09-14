from django.contrib import admin

from .models import DoctorWhatsAppAccount, WhatsAppSession


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = ("phone", "state", "updated_at")
    list_filter = ("state",)
    search_fields = ("phone",)


@admin.register(DoctorWhatsAppAccount)
class DoctorWhatsAppAccountAdmin(admin.ModelAdmin):
    list_display = (
        "doctor",
        "display_phone",
        "phone_number_id",
        "status",
        "connected_at",
        "updated_at",
    )
    list_filter = ("status",)
    search_fields = (
        "display_phone",
        "phone_number_id",
        "waba_id",
        "doctor__first_name",
        "doctor__last_name",
    )
    readonly_fields = ("created_at", "updated_at", "connected_at")
