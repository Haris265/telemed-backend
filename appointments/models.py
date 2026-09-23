from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone

from catalog.models import Clinic, DoctorProfile
from patients.models import PatientProfile


class Appointment(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CASH_AT_CLINIC = "cash_at_clinic", "Cash at Clinic"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        NOT_REQUIRED = "not_required", "Not Required"

    class PaymentOcrStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    scheduled_at = models.DateTimeField()
    token_date = models.DateField(db_index=True)
    token_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPCOMING,
    )
    notes = models.TextField(blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        blank=True,
        default="",
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NOT_REQUIRED,
    )
    payment_amount_expected = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    payment_amount_received = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    payment_reference = models.CharField(max_length=120, blank=True, default="")
    payment_slip = models.ImageField(
        upload_to="payment_slips/",
        blank=True,
        null=True,
    )
    payment_ocr_raw = models.JSONField(default=dict, blank=True)
    payment_ocr_status = models.CharField(
        max_length=16,
        choices=PaymentOcrStatus.choices,
        default=PaymentOcrStatus.SKIPPED,
    )
    payment_verified_at = models.DateTimeField(null=True, blank=True)
    visit_started_at = models.DateTimeField(null=True, blank=True)
    visit_ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            UniqueConstraint(
                fields=["doctor", "token_date", "token_number"],
                name="uniq_doctor_token_per_day",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.token_date:
            self.token_date = timezone.localdate()
        super().save(*args, **kwargs)

    @staticmethod
    def doctor_initials(doctor: DoctorProfile) -> str:
        parts = [doctor.first_name.strip(), doctor.last_name.strip()]
        initials = "".join(part[0].upper() for part in parts if part)
        return initials or "DR"

    @property
    def token_code(self) -> str:
        prefix = self.doctor_initials(self.doctor)
        return f"{prefix}-{self.token_number:03d}"

    def __str__(self):
        return f"{self.token_code} {self.patient} → {self.doctor} @ {self.token_date}"


class ClinicalNote(models.Model):
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name="clinical_note",
    )
    subjective = models.TextField(blank=True, default="")
    objective = models.TextField(blank=True, default="")
    assessment = models.TextField(blank=True, default="")
    plan = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SOAP for {self.appointment.token_code}"


class Prescription(models.Model):
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name="prescription",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Rx for {self.appointment.token_code}"


class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    medicine_name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100, blank=True, default="")
    frequency = models.CharField(max_length=100, blank=True, default="")
    duration = models.CharField(max_length=100, blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.medicine_name


class VisitAttachment(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        VOICE = "voice", "Voice"

    class SummaryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    file = models.FileField(upload_to="visit_attachments/")
    original_name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=100, blank=True, default="")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    sent_via_whatsapp = models.BooleanField(default=False)
    transcript_text = models.TextField(blank=True, default="")
    summary_text = models.TextField(blank=True, default="")
    summary_status = models.CharField(
        max_length=16,
        choices=SummaryStatus.choices,
        default=SummaryStatus.SKIPPED,
    )
    summary_error = models.CharField(max_length=500, blank=True, default="")
    follow_up_at = models.DateTimeField(null=True, blank=True)
    follow_up_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.kind} for {self.appointment.token_code}"
