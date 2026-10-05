import uuid

from django.db import models
from django.utils import timezone

from catalog.models import DoctorProfile
from patients.models import PatientProfile


class MarketingSubscription(models.Model):
    """Cash enablement so a doctor can run WhatsApp marketing campaigns."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="marketing_subscriptions",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Marketing {self.doctor} ({self.start_date} → {self.end_date})"

    @property
    def is_currently_valid(self) -> bool:
        today = timezone.localdate()
        return self.is_active and self.start_date <= today <= self.end_date


class MessageTemplate(models.Model):
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="message_templates",
    )
    name = models.CharField(max_length=120)
    body = models.TextField()
    header_image = models.ImageField(
        upload_to="marketing_templates/",
        blank=True,
        null=True,
    )
    meta_template_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Optional Meta-approved template name for outside 24h window.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.name} ({self.doctor})"


class MarketingCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="marketing_campaigns",
    )
    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.PROTECT,
        related_name="campaigns",
    )
    name = models.CharField(max_length=160, blank=True, default="")
    filter_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        label = self.name or f"Campaign {self.pk}"
        return f"{label} [{self.status}]"


class CampaignRecipient(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    campaign = models.ForeignKey(
        MarketingCampaign,
        on_delete=models.CASCADE,
        related_name="recipients",
    )
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaign_receipts",
    )
    phone = models.CharField(max_length=20, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error = models.CharField(max_length=500, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        unique_together = ("campaign", "phone")

    def __str__(self):
        return f"{self.phone} [{self.status}]"
