from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class AssistantPlan(models.Model):
    code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=64)
    max_bot_replies_per_patient_month = models.PositiveSmallIntegerField()
    max_text_messages_per_day = models.PositiveIntegerField()
    max_voice_notes_per_day = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_bot_replies_per_patient_month__gt=0),
                name="assistant_plan_patient_replies_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(max_text_messages_per_day__gt=0),
                name="assistant_plan_text_day_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(max_voice_notes_per_day__gte=0),
                name="assistant_plan_voice_day_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def clean(self):
        super().clean()
        if not self.is_active and self.pk:
            # Inactive plans cannot be newly assigned; validated on config.clean().
            pass
        if self.max_bot_replies_per_patient_month <= 0:
            raise ValidationError(
                {"max_bot_replies_per_patient_month": "Must be greater than 0."}
            )
        if self.max_text_messages_per_day <= 0:
            raise ValidationError(
                {"max_text_messages_per_day": "Must be greater than 0."}
            )


class ClinicAssistantConfig(models.Model):
    class WaStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CONNECTED = "connected", "Connected"
        DISCONNECTED = "disconnected", "Disconnected"
        ERROR = "error", "Error"

    clinic = models.OneToOneField(
        "catalog.Clinic",
        on_delete=models.CASCADE,
        related_name="assistant_config",
    )
    plan = models.ForeignKey(
        AssistantPlan,
        on_delete=models.PROTECT,
        related_name="clinic_configs",
        db_index=True,
    )
    is_enabled = models.BooleanField(default=False, db_index=True)
    system_prompt_extra = models.TextField(blank=True, default="")
    webhook_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    wa_status = models.CharField(
        max_length=16,
        choices=WaStatus.choices,
        default=WaStatus.PENDING,
        db_index=True,
    )
    waba_id = models.CharField(max_length=64, blank=True, default="")
    phone_number_id = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    display_phone = models.CharField(max_length=32, blank=True, default="")
    meta_app_id = models.CharField(max_length=64, blank=True, default="")
    access_token_encrypted = models.TextField(blank=True, default="")
    token_expires_at = models.DateTimeField(null=True, blank=True)
    meta_app_secret_encrypted = models.TextField(blank=True, default="")
    verify_token_encrypted = models.TextField(blank=True, default="")
    wa_connected_at = models.DateTimeField(null=True, blank=True)
    wa_last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phone_number_id"],
                condition=~models.Q(phone_number_id=""),
                name="uniq_assistant_phone_number_id_when_set",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(wa_status="connected")
                    | (
                        ~models.Q(phone_number_id="")
                        & ~models.Q(access_token_encrypted="")
                    )
                ),
                name="assistant_connected_requires_phone_and_token",
            ),
        ]

    def __str__(self) -> str:
        return f"Assistant({self.clinic_id}) plan={self.plan_id} enabled={self.is_enabled}"

    def clean(self):
        super().clean()
        extra = (self.system_prompt_extra or "").strip()
        if len(extra) > 1000:
            raise ValidationError(
                {"system_prompt_extra": "Style notes must be at most 1000 characters."}
            )
        self.system_prompt_extra = extra
        if self.plan_id and not self.plan.is_active:
            # Allow existing assignments; only block new assignment of inactive plan.
            if not self.pk:
                raise ValidationError(
                    {"plan": "Cannot assign an inactive plan to a new clinic config."}
                )
            else:
                try:
                    previous = ClinicAssistantConfig.objects.only("plan_id").get(pk=self.pk)
                except ClinicAssistantConfig.DoesNotExist:
                    previous = None
                if previous and previous.plan_id != self.plan_id:
                    raise ValidationError(
                        {"plan": "Cannot assign an inactive plan."}
                    )

    def save(self, *args, **kwargs):
        if self.wa_last_error and len(self.wa_last_error) > 500:
            self.wa_last_error = self.wa_last_error[:500]
        self.full_clean()
        return super().save(*args, **kwargs)

    def set_access_token(self, plain: str) -> None:
        from .crypto import encrypt_token

        self.access_token_encrypted = encrypt_token(plain)

    def set_meta_app_secret(self, plain: str) -> None:
        from .crypto import encrypt_token

        self.meta_app_secret_encrypted = encrypt_token(plain)

    def set_verify_token(self, plain: str) -> None:
        from .crypto import encrypt_token

        self.verify_token_encrypted = encrypt_token(plain)

    def get_access_token(self) -> str:
        from .crypto import decrypt_secret

        return decrypt_secret(self.access_token_encrypted)

    def get_meta_app_secret(self) -> str:
        from .crypto import decrypt_secret

        return decrypt_secret(self.meta_app_secret_encrypted)

    def get_verify_token(self) -> str:
        from .crypto import decrypt_secret

        return decrypt_secret(self.verify_token_encrypted)
