"""Audience filtering and campaign send logic."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from appointments.models import Appointment
from catalog.models import DoctorProfile
from patients.models import PatientProfile
from patients.serializers import normalize_phone

from .models import CampaignRecipient, MarketingCampaign, MessageTemplate

logger = logging.getLogger(__name__)


def doctor_has_marketing(doctor: DoctorProfile) -> bool:
    return bool(getattr(doctor, "marketing_enabled", False) or doctor.has_active_marketing())


def doctor_whatsapp_connected(doctor: DoctorProfile) -> bool:
    account = getattr(doctor, "whatsapp_account", None)
    if account is None:
        try:
            from whatsapp.models import DoctorWhatsAppAccount

            account = DoctorWhatsAppAccount.objects.filter(doctor=doctor).first()
        except Exception:
            account = None
    return bool(account and account.is_connected)


def _base_patient_qs(doctor: DoctorProfile) -> QuerySet[PatientProfile]:
    patient_ids = (
        Appointment.objects.filter(doctor=doctor)
        .exclude(status=Appointment.Status.CANCELLED)
        .values_list("patient_id", flat=True)
        .distinct()
    )
    return PatientProfile.objects.filter(id__in=patient_ids)


def filter_audience(
    doctor: DoctorProfile,
    filters: dict[str, Any] | None = None,
) -> QuerySet[PatientProfile]:
    """Return patients of this doctor matching optional filters."""
    filters = filters or {}
    qs = _base_patient_qs(doctor)

    clinic_id = filters.get("clinic_id")
    if clinic_id not in (None, "", 0, "0"):
        try:
            cid = int(clinic_id)
        except (TypeError, ValueError):
            cid = None
        if cid:
            qs = qs.filter(
                appointments__doctor=doctor,
                appointments__clinic_id=cid,
            ).distinct()

    city = (filters.get("city") or "").strip()
    if city:
        qs = qs.filter(
            appointments__doctor=doctor,
            appointments__clinic__city__icontains=city,
        ).distinct()

    area = (filters.get("area") or "").strip()
    if area:
        qs = qs.filter(
            appointments__doctor=doctor,
            appointments__clinic__area__icontains=area,
        ).distinct()

    has_upcoming = filters.get("has_upcoming")
    if has_upcoming in (True, "true", "1", 1):
        qs = qs.filter(
            appointments__doctor=doctor,
            appointments__status=Appointment.Status.UPCOMING,
            appointments__token_date__gte=timezone.localdate(),
        ).distinct()

    last_visit_days = filters.get("last_visit_days")
    if last_visit_days not in (None, "", 0, "0"):
        try:
            days = int(last_visit_days)
        except (TypeError, ValueError):
            days = 0
        if days > 0:
            since = timezone.now() - timedelta(days=days)
            qs = qs.filter(
                appointments__doctor=doctor,
                appointments__status=Appointment.Status.COMPLETED,
                appointments__visit_ended_at__gte=since,
            ).distinct()

    return qs.order_by("name", "id")


def audience_preview(
    doctor: DoctorProfile,
    filters: dict[str, Any] | None = None,
    *,
    sample_limit: int = 10,
) -> dict[str, Any]:
    qs = filter_audience(doctor, filters)
    sample = [
        {"uuid": str(p.uuid), "name": p.name, "phone": p.phone}
        for p in qs[:sample_limit]
    ]
    return {"count": qs.count(), "sample": sample}


def build_recipients(campaign: MarketingCampaign) -> int:
    """Create pending CampaignRecipient rows from filter_json. Returns count created."""
    patients = filter_audience(campaign.doctor, campaign.filter_json or {})
    created = 0
    for patient in patients.iterator():
        phone = normalize_phone(patient.phone or "")
        if len(phone) < 10:
            continue
        _, was_created = CampaignRecipient.objects.get_or_create(
            campaign=campaign,
            phone=phone,
            defaults={
                "patient": patient,
                "status": CampaignRecipient.Status.PENDING,
            },
        )
        if was_created:
            created += 1
    return created


def _send_one(
    client,
    recipient: CampaignRecipient,
    template: MessageTemplate,
) -> None:
    phone = recipient.phone
    body = (template.body or "").strip()
    meta_name = (template.meta_template_name or "").strip()

    if meta_name:
        result = client.send_template(
            phone,
            name=meta_name,
            language_code="en",
        )
        if result.get("error") or result.get("skipped"):
            raise RuntimeError(
                result.get("detail")
                or f"Meta template send failed ({result.get('status', '')})"
            )
        return

    # Free-form: image then text (24h window required by Meta).
    if template.header_image:
        try:
            path = template.header_image.path
        except Exception:
            path = ""
        if path:
            media_id = client.upload_media(path)
            if media_id:
                img = client.send_image(
                    phone, media_id=media_id, caption=body[:1024] if body else ""
                )
                if img.get("error"):
                    raise RuntimeError(f"Image send failed: {img}")
                if body and len(body) > 1024:
                    txt = client.send_text(phone, body)
                    if txt.get("error"):
                        raise RuntimeError(f"Text send failed: {txt}")
                return
    if not body:
        raise RuntimeError("Template has no body or image to send.")
    txt = client.send_text(phone, body)
    if txt.get("error") or txt.get("skipped"):
        raise RuntimeError(txt.get("detail") or "Text send failed / skipped.")


def process_campaign(campaign_id: int, *, batch_size: int = 50) -> dict[str, int]:
    """Send pending recipients for one campaign. Returns counts."""
    from whatsapp.meta_client import MetaWhatsAppClient

    try:
        campaign = MarketingCampaign.objects.select_related(
            "doctor", "template"
        ).get(pk=campaign_id)
    except MarketingCampaign.DoesNotExist:
        return {"sent": 0, "failed": 0, "skipped": 0}

    if not doctor_has_marketing(campaign.doctor):
        campaign.status = MarketingCampaign.Status.FAILED
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=["status", "finished_at", "updated_at"])
        return {"sent": 0, "failed": 0, "skipped": 0}

    if not doctor_whatsapp_connected(campaign.doctor):
        campaign.status = MarketingCampaign.Status.FAILED
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=["status", "finished_at", "updated_at"])
        return {"sent": 0, "failed": 0, "skipped": 0}

    if campaign.status in (
        MarketingCampaign.Status.DRAFT,
        MarketingCampaign.Status.QUEUED,
    ):
        campaign.status = MarketingCampaign.Status.SENDING
        campaign.started_at = campaign.started_at or timezone.now()
        campaign.save(update_fields=["status", "started_at", "updated_at"])

    client = MetaWhatsAppClient.for_doctor(campaign.doctor)
    template = campaign.template
    pending = list(
        campaign.recipients.filter(status=CampaignRecipient.Status.PENDING).order_by(
            "id"
        )[:batch_size]
    )

    counts = {"sent": 0, "failed": 0, "skipped": 0}
    for recipient in pending:
        try:
            _send_one(client, recipient, template)
            recipient.status = CampaignRecipient.Status.SENT
            recipient.error = ""
            recipient.sent_at = timezone.now()
            counts["sent"] += 1
        except Exception as exc:
            logger.exception(
                "Campaign %s send failed to %s", campaign.id, recipient.phone
            )
            recipient.status = CampaignRecipient.Status.FAILED
            recipient.error = str(exc)[:500]
            counts["failed"] += 1
        recipient.save(update_fields=["status", "error", "sent_at"])

    remaining = campaign.recipients.filter(
        status=CampaignRecipient.Status.PENDING
    ).exists()
    if not remaining:
        campaign.status = MarketingCampaign.Status.DONE
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=["status", "finished_at", "updated_at"])
    return counts
