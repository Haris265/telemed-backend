import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Package(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    clinic = models.ForeignKey(
        "catalog.Clinic",
        on_delete=models.CASCADE,
        related_name="packages",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    duration_days = models.PositiveIntegerField(default=30)
    max_doctors = models.PositiveIntegerField(default=5)
    max_patients = models.PositiveIntegerField(default=500)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["clinic", "code"],
                name="billing_package_clinic_code_uniq",
            ),
        ]

    def __str__(self):
        clinic_name = self.clinic.name if self.clinic_id else "—"
        return f"{self.name} ({self.code}) [{clinic_name}]"


class ClinicSubscription(models.Model):
    class Status(models.TextChoices):
        PENDING_CLINIC = "pending_clinic", "Pending clinic accept"
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    clinic = models.ForeignKey(
        "catalog.Clinic",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.clinic} → {self.package} ({self.status})"

    @property
    def is_currently_valid(self) -> bool:
        today = timezone.localdate()
        return (
            self.is_active
            and self.status == self.Status.ACTIVE
            and self.start_date <= today <= self.end_date
        )


class PurchaseRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    clinic = models.ForeignKey(
        "catalog.Clinic",
        on_delete=models.CASCADE,
        related_name="purchase_requests",
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="purchase_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_purchase_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.clinic} request {self.package} ({self.status})"


class Invoice(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PENDING_VERIFICATION = "pending_verification", "Pending verification"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    clinic = models.ForeignKey(
        "catalog.Clinic",
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    subscription = models.ForeignKey(
        ClinicSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invoices",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Invoice {self.clinic} {self.amount} ({self.status})"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    clinic = models.ForeignKey(
        "catalog.Clinic",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.CASH,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    subscription = models.ForeignKey(
        ClinicSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    paid_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-paid_at", "-id"]

    def __str__(self):
        return f"{self.clinic} {self.amount} ({self.method})"


class LedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        PAYMENT_IN = "payment_in", "Payment In"
        PACKAGE_CHARGE = "package_charge", "Package Charge"
        ADJUSTMENT = "adjustment", "Adjustment"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    clinic = models.ForeignKey(
        "catalog.Clinic",
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    entry_type = models.CharField(max_length=30, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    subscription = models.ForeignKey(
        ClinicSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "ledger entries"

    def __str__(self):
        return f"{self.clinic} {self.entry_type} {self.amount}"
