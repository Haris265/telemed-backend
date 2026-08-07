from django.contrib import admin

from .models import PatientProfile, SymptomCheck


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_verified", "user", "created_at")
    search_fields = ("name", "phone")
    list_filter = ("is_verified",)
    raw_id_fields = ("user",)


@admin.register(SymptomCheck)
class SymptomCheckAdmin(admin.ModelAdmin):
    list_display = ("patient", "urgency", "created_at")
    search_fields = ("patient__name", "patient__phone", "symptoms_text")
    list_filter = ("urgency",)
    raw_id_fields = ("patient",)
    filter_horizontal = ("recommended_specialities",)
