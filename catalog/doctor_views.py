from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsDoctor
from appointments.models import Appointment, ClinicalNote, Prescription, VisitAttachment
from appointments.serializers import (
    AppointmentDetailSerializer,
    AppointmentSerializer,
    ClinicalNoteSerializer,
    DoctorAppointmentStatusSerializer,
    PrescriptionSerializer,
    VisitAttachmentSerializer,
)
from patients.models import PatientProfile

from .models import DoctorAvailability, DoctorClinic, DoctorProfile
from .serializers import (
    DoctorAvailabilitySerializer,
    DoctorClinicCreateSerializer,
    DoctorClinicSerializer,
    DoctorClinicUpdateSerializer,
    DoctorProfileSerializer,
)

IMAGE_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
VOICE_MIMES = {
    "audio/m4a",
    "audio/mp4",
    "audio/mpeg",
    "audio/aac",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/3gpp",
    "audio/ogg",
    "application/octet-stream",
}


def get_doctor_appointment(doctor: DoctorProfile, pk: int) -> Appointment:
    return get_object_or_404(
        Appointment.objects.select_related("patient", "doctor", "clinic")
        .prefetch_related("prescription__items", "attachments")
        .select_related("clinical_note"),
        pk=pk,
        doctor=doctor,
    )


def _send_attachments_via_whatsapp(appointment: Appointment) -> None:
    """Soft-fail WhatsApp delivery of visit attachments to the patient."""
    import logging

    from whatsapp.meta_client import MetaWhatsAppClient

    logger = logging.getLogger(__name__)
    attachments = list(
        appointment.attachments.filter(sent_via_whatsapp=False).order_by("created_at")
    )
    if not attachments:
        return

    phone = "".join(ch for ch in (appointment.patient.phone or "") if ch.isdigit())
    if not phone:
        logger.warning(
            "No patient phone for appointment %s; skip WA media", appointment.id
        )
        return

    client = MetaWhatsAppClient()
    doctor_name = appointment.doctor.full_name
    token = appointment.token_code
    client.send_text(
        phone,
        f"Visit media from Dr. {doctor_name} (Token {token}).",
    )
    for att in attachments:
        try:
            path = att.file.path
        except Exception:
            logger.exception("Attachment %s has no local path", att.id)
            continue
        mime = att.mime_type or ""
        media_id = client.upload_media(path, mime)
        if att.kind == VisitAttachment.Kind.IMAGE:
            result = client.send_image(
                phone,
                media_id=media_id,
                caption=f"Dr. {doctor_name} — {token}",
            )
        else:
            result = client.send_audio(phone, media_id=media_id)
        if not result.get("error"):
            att.sent_via_whatsapp = True
            att.save(update_fields=["sent_via_whatsapp"])
        else:
            logger.error("WA send failed for attachment %s: %s", att.id, result)


class DoctorMeView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        doctor = request.user.doctor_profile
        return Response(DoctorProfileSerializer(doctor).data)


class DoctorClinicListCreateView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        doctor = request.user.doctor_profile
        # Ensure legacy single-clinic FK is mirrored in DoctorClinic.
        if doctor.clinic_id and not doctor.doctor_clinics.filter(
            clinic_id=doctor.clinic_id
        ).exists():
            DoctorClinic.objects.get_or_create(
                doctor=doctor,
                clinic_id=doctor.clinic_id,
                defaults={"is_primary": True},
            )
        links = (
            doctor.doctor_clinics.select_related("clinic")
            .prefetch_related("clinic__availabilities")
            .order_by("-created_at", "-id")
        )
        return Response(DoctorClinicSerializer(links, many=True).data)

    def post(self, request):
        doctor = request.user.doctor_profile
        serializer = DoctorClinicCreateSerializer(
            data=request.data, context={"doctor": doctor}
        )
        serializer.is_valid(raise_exception=True)
        link = serializer.save()
        return Response(
            DoctorClinicSerializer(link).data,
            status=status.HTTP_201_CREATED,
        )


class DoctorClinicDetailView(APIView):
    permission_classes = [IsDoctor]

    def get_link(self, request, pk: int) -> DoctorClinic:
        return get_object_or_404(
            DoctorClinic.objects.select_related("clinic"),
            pk=pk,
            doctor=request.user.doctor_profile,
        )

    def get(self, request, pk: int):
        return Response(DoctorClinicSerializer(self.get_link(request, pk)).data)

    def patch(self, request, pk: int):
        link = self.get_link(request, pk)
        serializer = DoctorClinicUpdateSerializer(link, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        link = serializer.save()
        return Response(DoctorClinicSerializer(link).data)

    def delete(self, request, pk: int):
        link = self.get_link(request, pk)
        doctor = request.user.doctor_profile
        clinic = link.clinic
        DoctorAvailability.objects.filter(doctor=doctor, clinic=clinic).delete()
        was_primary = link.is_primary
        link.delete()
        if was_primary or doctor.clinic_id == clinic.id:
            next_link = doctor.doctor_clinics.select_related("clinic").first()
            doctor.clinic = next_link.clinic if next_link else None
            doctor.save(update_fields=["clinic"])
            if next_link and not next_link.is_primary:
                next_link.is_primary = True
                next_link.save(update_fields=["is_primary"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class DoctorClinicAvailabilityListCreateView(APIView):
    permission_classes = [IsDoctor]

    def get_link(self, request, pk: int) -> DoctorClinic:
        return get_object_or_404(
            DoctorClinic.objects.select_related("clinic"),
            pk=pk,
            doctor=request.user.doctor_profile,
        )

    def get(self, request, pk: int):
        link = self.get_link(request, pk)
        slots = DoctorAvailability.objects.filter(
            doctor=link.doctor, clinic=link.clinic
        ).order_by("weekday", "start_time")
        return Response(DoctorAvailabilitySerializer(slots, many=True).data)

    def post(self, request, pk: int):
        link = self.get_link(request, pk)
        data = {**request.data, "clinic": link.clinic_id}
        serializer = DoctorAvailabilitySerializer(data=data)
        serializer.is_valid(raise_exception=True)
        slot = serializer.save(doctor=link.doctor, clinic=link.clinic)
        return Response(
            DoctorAvailabilitySerializer(slot).data,
            status=status.HTTP_201_CREATED,
        )


class DoctorClinicAvailabilityReplaceView(APIView):
    """Replace full weekly schedule for a clinic in one request."""

    permission_classes = [IsDoctor]

    def put(self, request, pk: int):
        link = get_object_or_404(
            DoctorClinic.objects.select_related("clinic"),
            pk=pk,
            doctor=request.user.doctor_profile,
        )
        slots = request.data.get("slots")
        if not isinstance(slots, list):
            return Response(
                {"detail": "slots must be a list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated = []
        for item in slots:
            serializer = DoctorAvailabilitySerializer(
                data={**item, "clinic": link.clinic_id}
            )
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            validated.append(
                {
                    "weekday": data["weekday"],
                    "start_time": data["start_time"],
                    "end_time": data["end_time"],
                    "is_active": data.get("is_active", True),
                }
            )

        DoctorAvailability.objects.filter(
            doctor=link.doctor, clinic=link.clinic
        ).delete()
        objs = [
            DoctorAvailability(doctor=link.doctor, clinic=link.clinic, **data)
            for data in validated
        ]
        DoctorAvailability.objects.bulk_create(objs)
        result = DoctorAvailability.objects.filter(
            doctor=link.doctor, clinic=link.clinic
        ).order_by("weekday", "start_time")
        return Response(DoctorAvailabilitySerializer(result, many=True).data)


class DoctorDashboardView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        doctor = request.user.doctor_profile
        today = timezone.localdate()

        base_qs = Appointment.objects.filter(doctor=doctor)
        today_qs = base_qs.filter(token_date=today)

        upcoming_today = (
            today_qs.filter(status=Appointment.Status.UPCOMING)
            .select_related("patient", "doctor")
            .order_by("token_number", "scheduled_at")
        )
        future_bookings = base_qs.filter(
            token_date__gt=today,
            status=Appointment.Status.UPCOMING,
        ).count()

        completed_patients = (
            base_qs.filter(status=Appointment.Status.COMPLETED)
            .values("patient_id")
            .distinct()
            .count()
        )

        return Response(
            {
                "today_upcoming": today_qs.filter(
                    status=Appointment.Status.UPCOMING
                ).count(),
                "today_completed": today_qs.filter(
                    status=Appointment.Status.COMPLETED
                ).count(),
                "today_rejected": today_qs.filter(
                    status=Appointment.Status.REJECTED
                ).count(),
                "future_bookings": future_bookings,
                "total_patients_seen": completed_patients,
                "upcoming_today": AppointmentSerializer(upcoming_today, many=True).data,
            }
        )


class DoctorAppointmentListView(generics.ListAPIView):
    permission_classes = [IsDoctor]
    serializer_class = AppointmentSerializer
    pagination_class = None

    def get_queryset(self):
        doctor = self.request.user.doctor_profile
        qs = Appointment.objects.filter(doctor=doctor).select_related(
            "patient", "doctor"
        )
        today = timezone.localdate()

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        today_only = self.request.query_params.get("today")

        if today_only and today_only.lower() in ("1", "true", "yes"):
            qs = qs.filter(token_date=today)
        elif date_from:
            qs = qs.filter(token_date__gte=date_from)
        elif date_to:
            qs = qs.filter(token_date__lte=date_to)
        else:
            upcoming_default = self.request.query_params.get("upcoming")
            if upcoming_default is None or upcoming_default.lower() in (
                "1",
                "true",
                "yes",
            ):
                qs = qs.filter(token_date__gte=today)

        return qs.order_by("token_date", "token_number", "scheduled_at")


class DoctorAppointmentDetailView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        return Response(
            AppointmentDetailSerializer(appointment, context={"request": request}).data
        )

    def patch(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        prev_status = appointment.status
        serializer = DoctorAppointmentStatusSerializer(
            appointment, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        appointment.refresh_from_db()
        if (
            appointment.status == Appointment.Status.COMPLETED
            and appointment.visit_started_at
            and not appointment.visit_ended_at
        ):
            appointment.visit_ended_at = timezone.now()
            appointment.save(update_fields=["visit_ended_at", "updated_at"])
        if (
            appointment.status == Appointment.Status.COMPLETED
            and prev_status != Appointment.Status.COMPLETED
        ):
            try:
                _send_attachments_via_whatsapp(appointment)
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "WhatsApp attachment delivery failed for appointment %s",
                    appointment.id,
                )
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        return Response(
            AppointmentDetailSerializer(appointment, context={"request": request}).data
        )


class DoctorAppointmentStartVisitView(APIView):
    permission_classes = [IsDoctor]

    def post(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        if appointment.status != Appointment.Status.UPCOMING:
            return Response(
                {"detail": "Only upcoming visits can be started."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if appointment.visit_started_at:
            return Response(
                {"detail": "Visit already started."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appointment.visit_started_at = timezone.now()
        appointment.save(update_fields=["visit_started_at", "updated_at"])
        return Response(
            AppointmentDetailSerializer(appointment, context={"request": request}).data
        )


class DoctorAppointmentEndVisitView(APIView):
    permission_classes = [IsDoctor]

    def post(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        if not appointment.visit_started_at:
            return Response(
                {"detail": "Start the visit before ending it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if appointment.visit_ended_at:
            return Response(
                {"detail": "Visit already ended."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        appointment.visit_ended_at = timezone.now()
        appointment.save(update_fields=["visit_ended_at", "updated_at"])
        return Response(
            AppointmentDetailSerializer(appointment, context={"request": request}).data
        )


class DoctorAppointmentAttachmentListCreateView(APIView):
    permission_classes = [IsDoctor]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        data = VisitAttachmentSerializer(
            appointment.attachments.all(),
            many=True,
            context={"request": request},
        ).data
        return Response(data)

    def post(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        if appointment.status not in (
            Appointment.Status.UPCOMING,
            Appointment.Status.COMPLETED,
        ):
            return Response(
                {"detail": "Cannot attach media to this visit."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        kind = (request.data.get("kind") or "").strip().lower()
        upload = request.FILES.get("file")
        if kind not in (VisitAttachment.Kind.IMAGE, VisitAttachment.Kind.VOICE):
            return Response(
                {"kind": "Must be 'image' or 'voice'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload:
            return Response(
                {"file": "File is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mime = (upload.content_type or "").lower()
        if kind == VisitAttachment.Kind.IMAGE and mime not in IMAGE_MIMES:
            # Some clients omit mime — allow by extension
            name = (upload.name or "").lower()
            if not name.endswith((".jpg", ".jpeg", ".png", ".webp")):
                return Response(
                    {"file": "Image must be JPEG, PNG, or WebP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            mime = mime or "image/jpeg"
        if kind == VisitAttachment.Kind.VOICE and mime not in VOICE_MIMES:
            name = (upload.name or "").lower()
            if not name.endswith((".m4a", ".mp4", ".mp3", ".aac", ".wav", ".webm", ".ogg", ".3gp")):
                return Response(
                    {"file": "Unsupported audio format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            mime = mime or "audio/m4a"

        duration = request.data.get("duration_seconds")
        duration_int = None
        if duration not in (None, ""):
            try:
                duration_int = max(0, int(duration))
            except (TypeError, ValueError):
                return Response(
                    {"duration_seconds": "Must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        att = VisitAttachment.objects.create(
            appointment=appointment,
            kind=kind,
            file=upload,
            original_name=upload.name or "",
            mime_type=mime,
            duration_seconds=duration_int,
        )
        return Response(
            VisitAttachmentSerializer(att, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class DoctorAppointmentAttachmentDetailView(APIView):
    permission_classes = [IsDoctor]

    def delete(self, request, pk, attachment_id):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        att = get_object_or_404(
            VisitAttachment, pk=attachment_id, appointment=appointment
        )
        if att.file:
            att.file.delete(save=False)
        att.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DoctorClinicalNoteView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        try:
            return Response(ClinicalNoteSerializer(appointment.clinical_note).data)
        except ClinicalNote.DoesNotExist:
            return Response(
                {
                    "subjective": "",
                    "objective": "",
                    "assessment": "",
                    "plan": "",
                }
            )

    def put(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        note, _ = ClinicalNote.objects.get_or_create(appointment=appointment)
        serializer = ClinicalNoteSerializer(note, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DoctorPrescriptionView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        try:
            return Response(PrescriptionSerializer(appointment.prescription).data)
        except Prescription.DoesNotExist:
            return Response({"notes": "", "items": []})

    def put(self, request, pk):
        appointment = get_doctor_appointment(request.user.doctor_profile, pk)
        prescription, _ = Prescription.objects.get_or_create(appointment=appointment)
        serializer = PrescriptionSerializer(prescription, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DoctorPatientListView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        doctor = request.user.doctor_profile
        today = timezone.localdate()

        patient_ids = (
            Appointment.objects.filter(
                doctor=doctor,
                token_date__gte=today,
            )
            .values_list("patient_id", flat=True)
            .distinct()
        )

        patients = PatientProfile.objects.filter(id__in=patient_ids).annotate(
            upcoming_count=Count(
                "appointments",
                filter=Q(
                    appointments__doctor=doctor,
                    appointments__status=Appointment.Status.UPCOMING,
                    appointments__token_date__gte=today,
                ),
            ),
            total_visits=Count(
                "appointments",
                filter=Q(
                    appointments__doctor=doctor,
                    appointments__status=Appointment.Status.COMPLETED,
                ),
            ),
        )

        results = []
        for patient in patients:
            next_appt = (
                Appointment.objects.filter(
                    doctor=doctor,
                    patient=patient,
                    status=Appointment.Status.UPCOMING,
                    token_date__gte=today,
                )
                .order_by("token_date", "token_number")
                .first()
            )
            results.append(
                {
                    "uuid": str(patient.uuid),
                    "name": patient.name,
                    "phone": patient.phone,
                    "upcoming_count": patient.upcoming_count,
                    "total_visits": patient.total_visits,
                    "next_appointment": (
                        AppointmentSerializer(next_appt).data if next_appt else None
                    ),
                }
            )

        results.sort(key=lambda p: (p["next_appointment"] or {}).get("token_date", "9999"))
        return Response(results)


class DoctorPatientDetailView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request, uuid):
        doctor = request.user.doctor_profile
        patient = get_object_or_404(PatientProfile, uuid=uuid)

        appointments = (
            Appointment.objects.filter(doctor=doctor, patient=patient)
            .select_related("patient", "doctor")
            .prefetch_related("prescription__items", "attachments")
            .select_related("clinical_note")
            .order_by("-token_date", "-token_number")
        )

        completed = appointments.filter(status=Appointment.Status.COMPLETED)
        last_completed = completed.first()
        rejected_count = appointments.filter(status=Appointment.Status.REJECTED).count()
        total_count = appointments.count()

        next_upcoming = (
            appointments.filter(
                status=Appointment.Status.UPCOMING,
                token_date__gte=timezone.localdate(),
            )
            .order_by("token_date", "token_number")
            .first()
        )

        return Response(
            {
                "uuid": str(patient.uuid),
                "name": patient.name,
                "phone": patient.phone,
                "total_visits": completed.count(),
                "total_appointments": total_count,
                "rejected_count": rejected_count,
                "rejection_rate": (
                    round(rejected_count / total_count * 100, 1) if total_count else 0
                ),
                "last_visit_date": (
                    last_completed.token_date.isoformat() if last_completed else None
                ),
                "last_clinical_note": (
                    ClinicalNoteSerializer(last_completed.clinical_note).data
                    if last_completed
                    and ClinicalNote.objects.filter(
                        appointment=last_completed
                    ).exists()
                    else None
                ),
                "last_prescription": (
                    PrescriptionSerializer(last_completed.prescription).data
                    if last_completed
                    and Prescription.objects.filter(
                        appointment=last_completed
                    ).exists()
                    else None
                ),
                "next_appointment": (
                    AppointmentSerializer(next_upcoming).data if next_upcoming else None
                ),
                "visit_history": AppointmentDetailSerializer(
                    appointments, many=True, context={"request": request}
                ).data,
            }
        )
