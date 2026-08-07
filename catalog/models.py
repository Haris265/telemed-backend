from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid


class Speciality(models.Model):
    name = models.CharField(max_length=120, unique=True)
    icon = models.ImageField(upload_to="specialities/", blank=True, null=True)
    icon_url = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "specialities"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def display_icon(self):
        if self.icon:
            return self.icon.url
        return self.icon_url


class Clinic(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100, blank=True, default="")
    area = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Neighbourhood/area name used for map search (e.g. Gulshan, Clifton).",
    )
    phone = models.CharField(max_length=30, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class DoctorProfile(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    specialities = models.ManyToManyField(Speciality, related_name="doctors", blank=True)
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctors",
    )
    session_time = models.PositiveIntegerField(
        default=15,
        help_text="Consultation session length in minutes",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Dr. {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def has_active_subscription(self) -> bool:
        today = timezone.localdate()
        return self.subscriptions.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        ).exists()

    @property
    def subscription_status(self) -> str:
        today = timezone.localdate()
        active = self.subscriptions.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        ).exists()
        if active:
            return "subscribed"
        if self.subscriptions.exists():
            return "expired"
        return "none"


class DoctorSubscription(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="subscriptions",
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
        return f"{self.doctor} ({self.start_date} → {self.end_date})"

    @property
    def is_currently_valid(self) -> bool:
        today = timezone.localdate()
        return self.is_active and self.start_date <= today <= self.end_date


class DoctorClinic(models.Model):
    """Links a doctor to clinics they practice at (supports multiple clinics)."""

    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="doctor_clinics",
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name="doctor_clinics",
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        unique_together = ("doctor", "clinic")
        verbose_name = "doctor clinic"
        verbose_name_plural = "doctor clinics"

    def __str__(self):
        return f"{self.doctor} @ {self.clinic}"


class DoctorAvailability(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="availabilities",
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="availabilities",
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name_plural = "doctor availabilities"

    def __str__(self):
        clinic = f" @ {self.clinic}" if self.clinic_id else ""
        return (
            f"{self.doctor}{clinic} — {self.get_weekday_display()} "
            f"{self.start_time}-{self.end_time}"
        )
