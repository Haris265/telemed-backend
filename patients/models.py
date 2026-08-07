import uuid

from django.conf import settings
from django.db import models

from catalog.models import Speciality


class PatientProfile(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_profile",
    )
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.name} ({self.phone})"


class SymptomCheck(models.Model):
    class Urgency(models.TextChoices):
        ROUTINE = "routine", "Routine"
        URGENT = "urgent", "Urgent"
        EMERGENCY = "emergency", "Emergency"

    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="symptom_checks",
    )
    symptoms_text = models.TextField()
    urgency = models.CharField(
        max_length=20,
        choices=Urgency.choices,
        default=Urgency.ROUTINE,
    )
    summary = models.TextField(blank=True, default="")
    recommended_specialities = models.ManyToManyField(
        Speciality,
        related_name="symptom_checks",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"SymptomCheck #{self.pk} ({self.patient})"
