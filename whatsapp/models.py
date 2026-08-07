from django.db import models


class WhatsAppSession(models.Model):
    class State(models.TextChoices):
        IDLE = "idle", "Idle"
        AWAITING_NAME = "awaiting_name", "Awaiting Name"
        AWAITING_OTP = "awaiting_otp", "Awaiting OTP"
        AWAITING_SPECIALITY = "awaiting_speciality", "Awaiting Speciality"
        AWAITING_DOCTOR = "awaiting_doctor", "Awaiting Doctor"
        AWAITING_CLINIC = "awaiting_clinic", "Awaiting Clinic"
        AWAITING_DATE = "awaiting_date", "Awaiting Date"
        AWAITING_SLOT = "awaiting_slot", "Awaiting Slot"
        AWAITING_CONFIRM = "awaiting_confirm", "Awaiting Confirm"
        MENU = "menu", "Menu"

    phone = models.CharField(max_length=20, unique=True, db_index=True)
    state = models.CharField(
        max_length=32,
        choices=State.choices,
        default=State.IDLE,
    )
    context = models.JSONField(default=dict, blank=True)
    last_message_id = models.CharField(max_length=128, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.phone} [{self.state}]"
