from django.db.models import Q
from django.utils import timezone
from rest_framework import generics

from accounts.permissions import IsAdmin
from patients.models import PatientProfile
from patients.serializers import PatientDetailSerializer, PatientProfileSerializer

from .models import Appointment
from .serializers import AppointmentSerializer, AppointmentWriteSerializer


class AdminAppointmentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AppointmentWriteSerializer
        return AppointmentSerializer

    def get_queryset(self):
        qs = Appointment.objects.select_related("patient", "doctor")
        status_param = self.request.query_params.get("status")
        doctor = self.request.query_params.get("doctor")
        patient = self.request.query_params.get("patient")
        q = self.request.query_params.get("q")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        today = self.request.query_params.get("today")
        if today and today.lower() in ("1", "true", "yes"):
            qs = qs.filter(token_date=timezone.localdate())
        if status_param:
            qs = qs.filter(status=status_param)
        if doctor:
            qs = qs.filter(doctor_id=doctor)
        if patient:
            qs = qs.filter(patient_id=patient)
        if date_from:
            qs = qs.filter(token_date__gte=date_from)
        if date_to:
            qs = qs.filter(token_date__lte=date_to)
        if q:
            qs = qs.filter(
                Q(patient__name__icontains=q)
                | Q(patient__phone__icontains=q)
                | Q(doctor__first_name__icontains=q)
                | Q(doctor__last_name__icontains=q)
            )
        return qs.order_by("-created_at", "-id")


class AdminAppointmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    queryset = Appointment.objects.select_related("patient", "doctor")

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return AppointmentWriteSerializer
        return AppointmentSerializer


class AdminPatientListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = PatientProfileSerializer

    def get_queryset(self):
        qs = PatientProfile.objects.all()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))
        return qs.order_by("-created_at", "-id")


class AdminPatientDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = PatientDetailSerializer
    queryset = PatientProfile.objects.all()
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
