import logging
from datetime import time

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsPatient
from appointments.models import Appointment, ClinicalNote, Prescription
from appointments.serializers import (
    AppointmentDetailSerializer,
    AppointmentSerializer,
    ClinicalNoteSerializer,
    PrescriptionSerializer,
)
from appointments.services import (
    book_token,
    lookup_patient_token,
    queue_info,
    upcoming_available_dates,
)
from catalog.models import Clinic, DoctorAvailability, DoctorClinic, DoctorProfile, Speciality
from catalog.serializers import (
    ClinicSerializer,
    DoctorAvailabilitySerializer,
    SpecialitySerializer,
)
from catalog.services.geo import haversine_km
from whatsapp.meta_client import MetaWhatsAppClient

from .models import PatientProfile, SymptomCheck
from .serializers import (
    PatientBookSerializer,
    PatientDoctorSerializer,
    PatientProfileSerializer,
    RequestOtpSerializer,
    SymptomCheckRequestSerializer,
    SymptomCheckResultSerializer,
    VerifyOtpSerializer,
    generate_otp,
)
from .services.symptom_triage import triage_symptoms

logger = logging.getLogger(__name__)


def _patient_for_user(user) -> PatientProfile | None:
    return getattr(user, "patient_profile", None) or PatientProfile.objects.filter(
        user=user
    ).first()


class ClinicInfoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        number = (settings.CLINIC_WHATSAPP_NUMBER or "").strip()
        digits = "".join(ch for ch in number if ch.isdigit())
        if not digits:
            digits = MetaWhatsAppClient().get_display_phone_digits()
        prefill = "2"
        link = f"https://wa.me/{digits}" if digits else ""
        if link and prefill:
            link = f"{link}?text={prefill}"
        return Response(
            {
                "whatsapp_number": digits,
                "whatsapp_link": link,
                "book_prefill": prefill,
                "webhook_path": "/api/whatsapp/webhook/",
            }
        )


class RequestOtpView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = RequestOtpSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        phone = ser.validated_data["phone"]
        otp = generate_otp()
        cache.set(f"otp:{phone}", otp, timeout=300)

        body = (
            f"Your Telemed login OTP is: {otp}\n"
            "It expires in 5 minutes."
        )
        try:
            MetaWhatsAppClient().send_text(phone, body)
        except Exception:
            logger.exception("Failed sending OTP WhatsApp to %s", phone)

        patient = PatientProfile.objects.filter(phone=phone).first()
        payload = {
            "detail": "OTP sent.",
            "phone": phone,
            "needs_name": patient is None or not (patient.name or "").strip(),
        }
        if settings.DEBUG:
            payload["otp"] = otp
        return Response(payload)


class VerifyOtpView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = VerifyOtpSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.save()
        return Response(data)


class MeView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)
        return Response(PatientProfileSerializer(patient).data)

    def patch(self, request):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)
        ser = PatientProfileSerializer(patient, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class PatientSpecialityListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsPatient]
    serializer_class = SpecialitySerializer
    pagination_class = None

    def get_queryset(self):
        return Speciality.objects.filter(is_active=True).order_by("name")


class PatientDoctorListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsPatient]
    serializer_class = PatientDoctorSerializer
    pagination_class = None

    def get_queryset(self):
        qs = (
            DoctorProfile.objects.filter(is_active=True)
            .prefetch_related("specialities")
            .order_by("first_name", "last_name")
        )
        speciality = self.request.query_params.get("speciality")
        if speciality:
            qs = qs.filter(specialities__id=speciality).distinct()
        return qs


class PatientDoctorAvailabilityView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request, uuid):
        doctor = DoctorProfile.objects.filter(uuid=uuid, is_active=True).first()
        if not doctor:
            return Response({"detail": "Doctor not found."}, status=404)

        clinic_param = request.query_params.get("clinic")
        clinic = None
        if clinic_param:
            try:
                clinic_id = int(clinic_param)
            except (TypeError, ValueError):
                return Response({"detail": "Invalid clinic id."}, status=400)
            clinic = Clinic.objects.filter(pk=clinic_id, is_active=True).first()
            if not clinic:
                return Response({"detail": "Clinic not found."}, status=404)
            if not DoctorClinic.objects.filter(doctor=doctor, clinic=clinic).exists():
                return Response(
                    {"detail": "Doctor is not linked to this clinic."},
                    status=400,
                )

        weekly_qs = DoctorAvailability.objects.filter(
            doctor=doctor, is_active=True, clinic__isnull=False
        )
        if clinic is not None:
            weekly_qs = weekly_qs.filter(clinic=clinic)
        weekly = weekly_qs.order_by("weekday", "start_time")
        dates = upcoming_available_dates(doctor, clinic=clinic)
        return Response(
            {
                "doctor": PatientDoctorSerializer(doctor).data,
                "clinic_id": clinic.id if clinic else None,
                "weekly": DoctorAvailabilitySerializer(weekly, many=True).data,
                "dates": dates,
            }
        )


class PatientDoctorClinicsView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request, uuid):
        doctor = DoctorProfile.objects.filter(uuid=uuid, is_active=True).first()
        if not doctor:
            return Response({"detail": "Doctor not found."}, status=404)
        # Mirror legacy single-clinic FK into DoctorClinic.
        if doctor.clinic_id and not DoctorClinic.objects.filter(
            doctor=doctor, clinic_id=doctor.clinic_id
        ).exists():
            DoctorClinic.objects.get_or_create(
                doctor=doctor,
                clinic_id=doctor.clinic_id,
                defaults={"is_primary": True},
            )
        links = (
            DoctorClinic.objects.filter(doctor=doctor, clinic__is_active=True)
            .select_related("clinic")
            .order_by("-is_primary", "clinic__name")
        )
        results = []
        for link in links:
            data = ClinicSerializer(link.clinic).data
            data["is_primary"] = link.is_primary
            data["has_schedule"] = DoctorAvailability.objects.filter(
                doctor=doctor, clinic=link.clinic, is_active=True
            ).exists()
            results.append(data)
        return Response({"doctor_uuid": str(doctor.uuid), "clinics": results})


class PatientAppointmentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)
        qs = (
            Appointment.objects.filter(patient=patient)
            .select_related("doctor", "clinic")
            .order_by("-token_date", "token_number", "-created_at")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(AppointmentSerializer(qs, many=True).data)

    def post(self, request):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)

        ser = PatientBookSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        doctor = ser.validated_data["doctor"]
        clinic = ser.validated_data["clinic"]
        token_date = ser.validated_data["token_date"]
        start_raw = ser.validated_data["start"]
        parts = [int(x) for x in start_raw.split(":")[:3]]
        start_time = time(*parts)

        notes = "Booked via App"
        symptoms = (ser.validated_data.get("symptoms") or "").strip()
        symptom_check_id = ser.validated_data.get("symptom_check_id")
        if symptom_check_id:
            check = SymptomCheck.objects.filter(
                pk=symptom_check_id, patient=patient
            ).first()
            if check:
                symptoms = check.symptoms_text.strip()
        if symptoms:
            notes = f"{notes}\nSymptoms: {symptoms}"

        try:
            appt = book_token(
                patient,
                doctor,
                token_date,
                start_time,
                slot_time=ser.validated_data.get("slot_time"),
                clinic=clinic,
                notes=notes,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "appointment": AppointmentSerializer(appt).data,
                "queue": queue_info(appt),
            },
            status=status.HTTP_201_CREATED,
        )


class PatientAppointmentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request, pk):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)

        appt = (
            Appointment.objects.filter(pk=pk, patient=patient)
            .select_related("patient", "doctor")
            .prefetch_related(
                "prescription__items",
                "doctor__specialities",
                "attachments",
            )
            .select_related("clinical_note")
            .first()
        )
        if not appt:
            return Response({"detail": "Appointment not found."}, status=404)

        return Response(
            AppointmentDetailSerializer(appt, context={"request": request}).data
        )


class PatientHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)

        appointments = (
            Appointment.objects.filter(patient=patient)
            .select_related("patient", "doctor")
            .prefetch_related(
                "prescription__items",
                "doctor__specialities",
                "attachments",
            )
            .select_related("clinical_note")
            .order_by("-token_date", "-token_number", "-created_at")
        )

        completed = appointments.filter(status=Appointment.Status.COMPLETED)
        last_completed = completed.first()

        doctors_seen = []
        seen_ids = set()
        for appt in completed.order_by("-token_date", "-token_number"):
            if appt.doctor_id in seen_ids:
                continue
            seen_ids.add(appt.doctor_id)
            doctor = appt.doctor
            doctors_seen.append(
                {
                    "id": doctor.id,
                    "uuid": str(doctor.uuid),
                    "full_name": doctor.full_name,
                    "specialities": [
                        {"id": s.id, "name": s.name}
                        for s in doctor.specialities.filter(is_active=True)
                    ],
                    "visit_count": completed.filter(doctor_id=doctor.id).count(),
                    "last_visit_date": (
                        completed.filter(doctor_id=doctor.id)
                        .order_by("-token_date")
                        .values_list("token_date", flat=True)
                        .first()
                        .isoformat()
                        if completed.filter(doctor_id=doctor.id).exists()
                        else None
                    ),
                }
            )

        return Response(
            {
                "total_visits": completed.count(),
                "total_appointments": appointments.count(),
                "doctors_seen_count": len(doctors_seen),
                "last_visit_date": (
                    last_completed.token_date.isoformat() if last_completed else None
                ),
                "last_clinical_note": (
                    ClinicalNoteSerializer(last_completed.clinical_note).data
                    if last_completed
                    and ClinicalNote.objects.filter(appointment=last_completed).exists()
                    else None
                ),
                "last_prescription": (
                    PrescriptionSerializer(last_completed.prescription).data
                    if last_completed
                    and Prescription.objects.filter(appointment=last_completed).exists()
                    else None
                ),
                "doctors_seen": doctors_seen,
                "visit_history": AppointmentDetailSerializer(
                    appointments, many=True, context={"request": request}
                ).data,
            }
        )


class PatientAppointmentQueueView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request, pk):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)
        appt = (
            Appointment.objects.filter(pk=pk, patient=patient)
            .select_related("doctor")
            .first()
        )
        if not appt:
            return Response({"detail": "Appointment not found."}, status=404)
        return Response(queue_info(appt))


class SymptomCheckView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def post(self, request):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)

        ser = SymptomCheckRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        symptoms = ser.validated_data["symptoms"]
        result = triage_symptoms(symptoms)

        check = SymptomCheck.objects.create(
            patient=patient,
            symptoms_text=symptoms,
            urgency=result.urgency,
            summary=result.summary,
        )
        if result.recommended_specialities:
            check.recommended_specialities.set(result.recommended_specialities)

        return Response(
            SymptomCheckResultSerializer(check).data,
            status=status.HTTP_201_CREATED,
        )


class NearbyClinicsView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request):
        try:
            lat = float(request.query_params.get("lat", ""))
            lng = float(request.query_params.get("lng", ""))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Query params lat and lng are required as numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return Response(
                {"detail": "lat/lng out of valid range."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        area_q = (request.query_params.get("area") or "").strip()
        match_mode = "area" if area_q else "nearby"

        try:
            radius_km = float(request.query_params.get("radius_km", "5"))
        except (TypeError, ValueError):
            radius_km = 5.0
        radius_km = max(0.5, min(radius_km, 25.0))

        results = []
        clinics = Clinic.objects.filter(is_active=True).annotate(
            doctor_count=Count(
                "doctor_clinics__doctor",
                filter=Q(doctor_clinics__doctor__is_active=True),
                distinct=True,
            )
        )
        if area_q:
            clinics = clinics.filter(area__icontains=area_q)

        for clinic in clinics:
            distance = haversine_km(
                lat,
                lng,
                float(clinic.latitude),
                float(clinic.longitude),
            )
            if distance <= radius_km:
                results.append(
                    {
                        "id": clinic.id,
                        "name": clinic.name,
                        "address": clinic.address,
                        "city": clinic.city,
                        "area": clinic.area,
                        "phone": clinic.phone,
                        "latitude": float(clinic.latitude),
                        "longitude": float(clinic.longitude),
                        "distance_km": round(distance, 2),
                        "doctor_count": clinic.doctor_count,
                    }
                )

        results.sort(key=lambda row: row["distance_km"])
        return Response(
            {
                "lat": lat,
                "lng": lng,
                "radius_km": radius_km,
                "area": area_q,
                "match_mode": match_mode,
                "count": len(results),
                "results": results,
            }
        )


class PatientClinicDetailView(APIView):
    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request, pk):
        clinic = Clinic.objects.filter(pk=pk, is_active=True).first()
        if not clinic:
            return Response({"detail": "Clinic not found."}, status=404)

        doctors = (
            DoctorProfile.objects.filter(
                is_active=True,
                doctor_clinics__clinic=clinic,
            )
            .prefetch_related("specialities")
            .distinct()
            .order_by("first_name", "last_name")
        )
        speciality_map = {}
        for doctor in doctors:
            for spec in doctor.specialities.all():
                if not spec.is_active:
                    continue
                if spec.id not in speciality_map:
                    speciality_map[spec.id] = {
                        "id": spec.id,
                        "name": spec.name,
                        "display_icon": spec.display_icon,
                        "is_active": spec.is_active,
                        "doctor_count": 0,
                    }
                speciality_map[spec.id]["doctor_count"] += 1

        specialities = sorted(speciality_map.values(), key=lambda s: s["name"])

        return Response(
            {
                "id": clinic.id,
                "name": clinic.name,
                "address": clinic.address,
                "city": clinic.city,
                "phone": clinic.phone,
                "latitude": float(clinic.latitude),
                "longitude": float(clinic.longitude),
                "specialities": specialities,
                "doctors": PatientDoctorSerializer(doctors, many=True).data,
            }
        )


class PatientTokenLookupView(APIView):
    """Search today's (or any) appointment by token number/code for live queue status."""

    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request):
        patient = _patient_for_user(request.user)
        if not patient:
            return Response({"detail": "Patient profile not found."}, status=404)

        q = (request.query_params.get("q") or request.query_params.get("token") or "").strip()
        if not q:
            return Response(
                {"detail": "Enter your token number (e.g. 5 or AH-005)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today_only = (request.query_params.get("today") or "1").lower() not in (
            "0",
            "false",
            "no",
        )
        appt = lookup_patient_token(patient, q, today_only=today_only)
        if not appt and today_only:
            # Fall back to any upcoming date if nothing today
            appt = lookup_patient_token(patient, q, today_only=False)

        if not appt:
            return Response(
                {
                    "detail": (
                        "No appointment found for that token. "
                        "Check the number on your booking."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(queue_info(appt))
