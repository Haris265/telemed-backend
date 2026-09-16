from django.conf import settings
from django.db import models


class WhatsAppSession(models.Model):
    class State(models.TextChoices):
        IDLE = "idle", "Idle"
        AWAITING_NAME = "awaiting_name", "Awaiting Name"
        AWAITING_OTP = "awaiting_otp", "Awaiting OTP"
        AWAITING_BOOKING_MODE = "awaiting_booking_mode", "Awaiting Booking Mode"
        AWAITING_SPECIALITY = "awaiting_speciality", "Awaiting Speciality"
        AWAITING_DOCTOR = "awaiting_doctor", "Awaiting Doctor"
        AWAITING_CLINIC = "awaiting_clinic", "Awaiting Clinic"
        AWAITING_CLINIC_DOCTOR = "awaiting_clinic_doctor", "Awaiting Clinic Doctor"
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


class DoctorWhatsAppAccount(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONNECTED = "connected", "Connected"
        DISCONNECTED = "disconnected", "Disconnected"
        ERROR = "error", "Error"

    doctor = models.OneToOneField(
        "catalog.DoctorProfile",
        on_delete=models.CASCADE,
        related_name="whatsapp_account",
    )
    waba_id = models.CharField(max_length=64, blank=True, default="")
    phone_number_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )
    display_phone = models.CharField(max_length=32, blank=True, default="")
    access_token_encrypted = models.TextField(blank=True, default="")
    token_expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    connected_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phone_number_id"],
                condition=~models.Q(phone_number_id=""),
                name="uniq_wa_phone_number_id_when_set",
            ),
        ]

    def __str__(self):
        return f"WA({self.doctor_id}) {self.display_phone or self.phone_number_id} [{self.status}]"

    @property
    def is_connected(self) -> bool:
        return (
            self.status == self.Status.CONNECTED
            and bool(self.phone_number_id)
            and bool(self.access_token_encrypted)
        )

    def set_access_token(self, plain: str) -> None:
        from .crypto import encrypt_token

        self.access_token_encrypted = encrypt_token(plain)

    def get_access_token(self) -> str:
        from .crypto import decrypt_token

        return decrypt_token(self.access_token_encrypted)
