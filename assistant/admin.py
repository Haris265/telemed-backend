from django import forms
from django.contrib import admin

from .models import AssistantPlan, ClinicAssistantConfig


class ClinicAssistantConfigForm(forms.ModelForm):
    access_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Write-only. Leave blank to keep the current token.",
    )
    meta_app_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Write-only. Leave blank to keep the current secret.",
    )
    verify_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Write-only. Leave blank to keep the current verify token.",
    )

    class Meta:
        model = ClinicAssistantConfig
        fields = (
            "clinic",
            "plan",
            "is_enabled",
            "system_prompt_extra",
            "wa_status",
            "waba_id",
            "phone_number_id",
            "display_phone",
            "meta_app_id",
            "token_expires_at",
            "wa_connected_at",
            "wa_last_error",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance and instance.pk:
            self.fields["access_token"].help_text += (
                f" Stored: {'set' if instance.access_token_encrypted else 'empty'}."
            )
            self.fields["meta_app_secret"].help_text += (
                f" Stored: {'set' if instance.meta_app_secret_encrypted else 'empty'}."
            )
            self.fields["verify_token"].help_text += (
                f" Stored: {'set' if instance.verify_token_encrypted else 'empty'}."
            )

    def save(self, commit=True):
        instance: ClinicAssistantConfig = super().save(commit=False)
        access = self.cleaned_data.get("access_token") or ""
        app_secret = self.cleaned_data.get("meta_app_secret") or ""
        verify = self.cleaned_data.get("verify_token") or ""
        if access:
            instance.set_access_token(access)
        if app_secret:
            instance.set_meta_app_secret(app_secret)
        if verify:
            instance.set_verify_token(verify)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(AssistantPlan)
class AssistantPlanAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "max_bot_replies_per_patient_month",
        "max_text_messages_per_day",
        "max_voice_notes_per_day",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("code",)


@admin.register(ClinicAssistantConfig)
class ClinicAssistantConfigAdmin(admin.ModelAdmin):
    form = ClinicAssistantConfigForm
    list_display = (
        "clinic",
        "plan",
        "is_enabled",
        "wa_status",
        "phone_number_id",
        "updated_at",
    )
    list_filter = ("is_enabled", "wa_status", "plan")
    search_fields = ("clinic__name", "phone_number_id", "display_phone")
    readonly_fields = ("webhook_key", "created_at", "updated_at")
    autocomplete_fields = ("clinic", "plan")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "clinic",
                    "plan",
                    "is_enabled",
                    "system_prompt_extra",
                    "webhook_key",
                )
            },
        ),
        (
            "WhatsApp (Phase 2)",
            {
                "fields": (
                    "wa_status",
                    "waba_id",
                    "phone_number_id",
                    "display_phone",
                    "meta_app_id",
                    "access_token",
                    "meta_app_secret",
                    "verify_token",
                    "token_expires_at",
                    "wa_connected_at",
                    "wa_last_error",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
