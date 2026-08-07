from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsDoctor
from appointments.models import Appointment
from appointments.serializers import AppointmentSerializer
from patients.models import PatientProfile

from .models import Clinic, DoctorAvailability, DoctorProfile, DoctorSubscription, Speciality
from .serializers import (
    ClinicSerializer,
    DoctorAvailabilitySerializer,
    DoctorOnboardingSerializer,
    DoctorProfileSerializer,
    DoctorSubscriptionSerializer,
    SpecialitySerializer,
)


class DashboardStatsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        today = timezone.localdate()

        upcoming_today = (
            Appointment.objects.filter(
                status=Appointment.Status.UPCOMING,
                token_date=today,
            )
            .select_related("patient", "doctor")
            .order_by("-created_at", "-id")[:5]
        )
        recent = (
            Appointment.objects.select_related("patient", "doctor")
            .order_by("-created_at", "-id")[:5]
        )

        return Response(
            {
                "total_doctors": DoctorProfile.objects.filter(is_active=True).count(),
                "total_patients": PatientProfile.objects.count(),
                "total_appointments": Appointment.objects.count(),
                "upcoming_today": AppointmentSerializer(upcoming_today, many=True).data,
                "recent_appointments": AppointmentSerializer(recent, many=True).data,
            }
        )


class SpecialityListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = SpecialitySerializer
    queryset = Speciality.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(name__icontains=q)
        active = self.request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class SpecialityDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = SpecialitySerializer
    queryset = Speciality.objects.all()


class ClinicListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClinicSerializer
    queryset = Clinic.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(address__icontains=q)
                | Q(city__icontains=q)
                | Q(phone__icontains=q)
            )
        active = self.request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class ClinicDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = ClinicSerializer
    queryset = Clinic.objects.all()


class DoctorOnboardingView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = DoctorOnboardingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = serializer.save()
        return Response(
            DoctorProfileSerializer(doctor).data,
            status=status.HTTP_201_CREATED,
        )


class DoctorListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = DoctorProfileSerializer

    def get_queryset(self):
        qs = DoctorProfile.objects.select_related("user").prefetch_related(
            "specialities",
            "subscriptions",
        )
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(user__email__icontains=q)
            )
        speciality = self.request.query_params.get("speciality")
        if speciality:
            qs = qs.filter(specialities__id=speciality)
        active = self.request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs.distinct()


class DoctorDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = DoctorProfileSerializer
    queryset = DoctorProfile.objects.select_related("user").prefetch_related(
        "specialities",
        "subscriptions",
    )
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def perform_destroy(self, instance):
        # Cascade removes DoctorProfile via OneToOne; drop login account too.
        user = instance.user
        user.delete()


class AdminSubscriptionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = DoctorSubscriptionSerializer

    def get_queryset(self):
        qs = DoctorSubscription.objects.select_related("doctor", "doctor__user")
        q = self.request.query_params.get("q")
        doctor = self.request.query_params.get("doctor")
        active = self.request.query_params.get("is_active")
        valid = self.request.query_params.get("valid")
        if q:
            qs = qs.filter(
                Q(doctor__first_name__icontains=q)
                | Q(doctor__last_name__icontains=q)
                | Q(doctor__user__email__icontains=q)
            )
        if doctor:
            qs = qs.filter(doctor_id=doctor)
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        if valid is not None:
            today = timezone.localdate()
            if valid.lower() in ("1", "true", "yes"):
                qs = qs.filter(is_active=True, start_date__lte=today, end_date__gte=today)
            else:
                qs = qs.exclude(is_active=True, start_date__lte=today, end_date__gte=today)
        return qs.order_by("-created_at", "-id")


class AdminSubscriptionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = DoctorSubscriptionSerializer
    queryset = DoctorSubscription.objects.select_related("doctor", "doctor__user")
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"


class AdminDeactivateUnsubscribedDoctorsView(APIView):
    """Deactivate doctors who currently have no valid cash subscription."""

    permission_classes = [IsAdmin]

    def post(self, request):
        today = timezone.localdate()
        active_sub_doctor_ids = DoctorSubscription.objects.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        ).values_list("doctor_id", flat=True)
        qs = DoctorProfile.objects.filter(is_active=True).exclude(id__in=active_sub_doctor_ids)
        deactivated = list(qs.values_list("id", flat=True))
        updated = qs.update(is_active=False)
        return Response(
            {
                "deactivated_count": updated,
                "doctor_ids": deactivated,
            }
        )


class DoctorAvailabilityListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsDoctor]
    serializer_class = DoctorAvailabilitySerializer

    def get_doctor(self):
        return self.request.user.doctor_profile

    def get_queryset(self):
        qs = DoctorAvailability.objects.filter(doctor=self.get_doctor())
        clinic_id = self.request.query_params.get("clinic")
        if clinic_id:
            qs = qs.filter(clinic_id=clinic_id)
        return qs.select_related("clinic")

    def perform_create(self, serializer):
        doctor = self.get_doctor()
        clinic = serializer.validated_data.get("clinic")
        if clinic and not doctor.doctor_clinics.filter(clinic=clinic).exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"clinic": "You are not linked to this clinic."})
        serializer.save(doctor=doctor)


class DoctorAvailabilityDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsDoctor]
    serializer_class = DoctorAvailabilitySerializer

    def get_queryset(self):
        return DoctorAvailability.objects.filter(
            doctor=self.request.user.doctor_profile
        ).select_related("clinic")

    def perform_update(self, serializer):
        doctor = self.request.user.doctor_profile
        clinic = serializer.validated_data.get("clinic")
        if clinic is not None and not doctor.doctor_clinics.filter(clinic=clinic).exists():
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"clinic": "You are not linked to this clinic."})
        serializer.save()


class AdminDoctorAvailabilityListView(generics.ListAPIView):
    """Admin read-only view of a doctor's weekly availability."""

    permission_classes = [IsAdmin]
    serializer_class = DoctorAvailabilitySerializer
    pagination_class = None

    def get_queryset(self):
        doctor_uuid = self.kwargs["uuid"]
        return DoctorAvailability.objects.filter(doctor__uuid=doctor_uuid).order_by(
            "weekday", "start_time"
        )
