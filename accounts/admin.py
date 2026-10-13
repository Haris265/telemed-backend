from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ClinicAdminProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("PatientCare", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("PatientCare", {"fields": ("role",)}),
    )


@admin.register(ClinicAdminProfile)
class ClinicAdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "clinic", "created_at")
    list_filter = ("clinic",)
    search_fields = ("user__username", "user__email", "clinic__name")
    raw_id_fields = ("user", "clinic")
