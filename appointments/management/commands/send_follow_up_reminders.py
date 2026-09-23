from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import VisitAttachment
from whatsapp.meta_client import MetaWhatsAppClient

logger = logging.getLogger(__name__)


def _digits(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


class Command(BaseCommand):
    help = (
        "Send WhatsApp reminders one day before follow-up visits "
        "extracted from voice note summaries."
    )

    def handle(self, *args, **options):
        now = timezone.localtime()
        tomorrow = (now + timedelta(days=1)).date()

        qs = (
            VisitAttachment.objects.filter(
                kind=VisitAttachment.Kind.VOICE,
                follow_up_at__isnull=False,
                follow_up_reminder_sent_at__isnull=True,
            )
            .select_related(
                "appointment",
                "appointment__patient",
                "appointment__doctor",
            )
            .order_by("follow_up_at", "id")
        )

        sent = 0
        skipped = 0
        failed = 0

        for att in qs:
            follow_local = timezone.localtime(att.follow_up_at)
            if follow_local.date() != tomorrow:
                continue

            appt = att.appointment
            patient = appt.patient
            doctor = appt.doctor
            phone = _digits(getattr(patient, "phone", "") or "")
            if not phone:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"attachment {att.id}: no patient phone, skip"
                    )
                )
                continue

            patient_name = (getattr(patient, "name", "") or "Patient").strip()
            doctor_name = (
                getattr(doctor, "full_name", None)
                or getattr(doctor, "name", None)
                or "Doctor"
            )
            when = follow_local.strftime("%d %b %Y, %I:%M %p")
            body = (
                f"Assalam o Alaikum {patient_name}. "
                f"Kal aapka visit scheduled hai ({when}). "
                f"Dr. {doctor_name} se milne ka khayal rakhein."
            )

            try:
                client = MetaWhatsAppClient.for_doctor(doctor)
                result = client.send_text(phone, body) or {}
                if result.get("skipped") or result.get("error"):
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"attachment {att.id}: WA skip/error {result}"
                        )
                    )
                    continue

                att.follow_up_reminder_sent_at = timezone.now()
                att.save(update_fields=["follow_up_reminder_sent_at"])
                sent += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"attachment {att.id}: reminder sent to {phone}"
                    )
                )
            except Exception as exc:
                failed += 1
                logger.exception(
                    "Follow-up reminder failed for attachment %s", att.id
                )
                self.stdout.write(
                    self.style.ERROR(f"attachment {att.id}: {exc}")
                )

        self.stdout.write(
            f"Done. sent={sent} skipped={skipped} failed={failed} "
            f"(tomorrow={tomorrow.isoformat()})"
        )
