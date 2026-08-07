from django.contrib import admin

from .models import (
    Appointment,
    ClinicalNote,
    Prescription,
    PrescriptionItem,
    VisitAttachment,
)


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0


class VisitAttachmentInline(admin.TabularInline):
    model = VisitAttachment
    extra = 0
    readonly_fields = ("created_at", "sent_via_whatsapp")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("appointment", "created_at")
    inlines = [PrescriptionItemInline]


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = ("appointment", "created_at")


@admin.register(VisitAttachment)
class VisitAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "appointment",
        "kind",
        "original_name",
        "mime_type",
        "sent_via_whatsapp",
        "created_at",
    )
    list_filter = ("kind", "sent_via_whatsapp")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "doctor",
        "scheduled_at",
        "status",
        "visit_started_at",
        "visit_ended_at",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "patient__name",
        "patient__phone",
        "doctor__first_name",
        "doctor__last_name",
    )
    readonly_fields = ("visit_started_at", "visit_ended_at")
    inlines = [VisitAttachmentInline]
