from datetime import datetime

from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsClinicAdmin, IsSuperAdmin
from appointments.models import Appointment
from appointments.serializers import AppointmentDetailSerializer, AppointmentSerializer
from catalog.models import Clinic, DoctorClinic, DoctorProfile, Speciality
from catalog.serializers import DoctorProfileSerializer, SpecialitySerializer

from .doctor_import import build_import_template_bytes, import_doctors_for_clinic
from .models import ClinicSubscription, LedgerEntry, Package, Payment, PurchaseRequest
from .serializers import (
    ApprovePurchaseSerializer,
    ClinicAdminCreateSerializer,
    ClinicAdminProfileSerializer,
    ClinicAppointmentCreateSerializer,
    ClinicAppointmentUpdateSerializer,
    ClinicBillingSerializer,
    ClinicDoctorCreateSerializer,
    ClinicDoctorDetailSerializer,
    ClinicDoctorUpdateSerializer,
    ClinicSubscriptionSerializer,
    DirectAssignSerializer,
    LedgerAdjustmentSerializer,
    LedgerEntrySerializer,
    PackageSerializer,
    PaymentSerializer,
    PurchaseRequestCreateSerializer,
    PurchaseRequestSerializer,
    RejectPurchaseSerializer,
)
from .services import (
    active_subscription_summary,
    cash_collected_since,
    clinic_ledger_balance,
    clinic_payment_summary,
)


class SuperadminDashboardView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)
        month_start_dt = timezone.make_aware(datetime.combine(month_start, datetime.min.time()))

        return Response(
            {
                "active_subscriptions": ClinicSubscription.objects.filter(
                    status=ClinicSubscription.Status.ACTIVE,
                    is_active=True,
                    start_date__lte=today,
                    end_date__gte=today,
                ).count(),
                "pending_requests": PurchaseRequest.objects.filter(
                    status=PurchaseRequest.Status.PENDING
                ).count(),
                "total_packages": Package.objects.filter(is_active=True).count(),
                "total_clinics": Clinic.objects.filter(is_active=True).count(),
                "cash_collected_month": str(cash_collected_since(month_start_dt)),
                "recent_payments": PaymentSerializer(
                    Payment.objects.select_related("clinic", "recorded_by").order_by(
                        "-paid_at"
                    )[:5],
                    many=True,
                ).data,
                "pending_request_list": PurchaseRequestSerializer(
                    PurchaseRequest.objects.filter(status=PurchaseRequest.Status.PENDING)
                    .select_related("clinic", "package", "requested_by")
                    .order_by("-created_at")[:5],
                    many=True,
                ).data,
            }
        )


class PackageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = PackageSerializer
    queryset = Package.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        active = self.request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class PackageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = PackageSerializer
    queryset = Package.objects.all()
    lookup_field = "uuid"

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            # Soft-deactivate when package has subscription/request history
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])


class SuperadminClinicListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = ClinicBillingSerializer
    queryset = Clinic.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(city__icontains=q)
                | Q(phone__icontains=q)
                | Q(owner_name__icontains=q)
            )
        active = self.request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class SuperadminClinicDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = ClinicBillingSerializer
    queryset = Clinic.objects.all()


class ClinicAdminCreateView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        serializer = ClinicAdminCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(
            ClinicAdminProfileSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )


class PurchaseRequestListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = PurchaseRequestSerializer

    def get_queryset(self):
        qs = PurchaseRequest.objects.select_related(
            "clinic", "package", "requested_by", "reviewed_by"
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        clinic_id = self.request.query_params.get("clinic")
        if clinic_id:
            qs = qs.filter(clinic_id=clinic_id)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(clinic__name__icontains=q) | Q(package__name__icontains=q)
            )
        return qs


class PurchaseRequestApproveView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request, uuid):
        try:
            purchase_request = PurchaseRequest.objects.select_related(
                "clinic", "package"
            ).get(uuid=uuid)
        except PurchaseRequest.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ApprovePurchaseSerializer(
            data=request.data,
            context={"request": request, "purchase_request": purchase_request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            result = serializer.save()
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "payment": PaymentSerializer(result["payment"]).data,
                "subscription": ClinicSubscriptionSerializer(result["subscription"]).data,
            }
        )


class PurchaseRequestRejectView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request, uuid):
        try:
            purchase_request = PurchaseRequest.objects.get(uuid=uuid)
        except PurchaseRequest.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = RejectPurchaseSerializer(
            data=request.data,
            context={"request": request, "purchase_request": purchase_request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            updated = serializer.save()
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PurchaseRequestSerializer(updated).data)


class DirectAssignView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        serializer = DirectAssignSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {
                "payment": PaymentSerializer(result["payment"]).data,
                "subscription": ClinicSubscriptionSerializer(result["subscription"]).data,
            },
            status=status.HTTP_201_CREATED,
        )


class SubscriptionListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = ClinicSubscriptionSerializer

    def get_queryset(self):
        qs = ClinicSubscription.objects.select_related("clinic", "package")
        clinic_id = self.request.query_params.get("clinic")
        if clinic_id:
            qs = qs.filter(clinic_id=clinic_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class PaymentListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.select_related("clinic", "recorded_by")
        clinic_id = self.request.query_params.get("clinic")
        if clinic_id:
            qs = qs.filter(clinic_id=clinic_id)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(clinic__name__icontains=q)
        return qs


class LedgerListView(generics.ListAPIView):
    permission_classes = [IsSuperAdmin]
    serializer_class = LedgerEntrySerializer

    def get_queryset(self):
        qs = LedgerEntry.objects.select_related("clinic", "created_by")
        clinic_id = self.request.query_params.get("clinic")
        if clinic_id:
            qs = qs.filter(clinic_id=clinic_id)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        clinic_id = request.query_params.get("clinic")
        balance = None
        active_sub = None
        payment_summary = None
        if clinic_id:
            try:
                clinic = Clinic.objects.get(pk=clinic_id)
                balance = str(clinic_ledger_balance(clinic))
                active_sub = active_subscription_summary(clinic)
                payment_summary = clinic_payment_summary(clinic)
            except Clinic.DoesNotExist:
                balance = None
                active_sub = None
                payment_summary = None
        if isinstance(response.data, dict):
            response.data["ledger_balance"] = balance
            response.data["active_subscription"] = active_sub
            response.data["payment_summary"] = payment_summary
        else:
            response.data = {
                "results": response.data,
                "ledger_balance": balance,
                "active_subscription": active_sub,
                "payment_summary": payment_summary,
                "count": len(response.data),
                "next": None,
                "previous": None,
            }
        return response


class LedgerAdjustmentView(APIView):
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        serializer = LedgerAdjustmentSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


# --- Clinic portal ---


def _clinic_for(request):
    return request.user.clinic_admin_profile.clinic


class ClinicMeView(APIView):
    permission_classes = [IsClinicAdmin]

    def get(self, request):
        clinic = _clinic_for(request)
        data = ClinicBillingSerializer(clinic).data
        data["ledger_balance"] = str(clinic_ledger_balance(clinic))
        return Response(data)


class ClinicPackageListView(generics.ListAPIView):
    permission_classes = [IsClinicAdmin]
    serializer_class = PackageSerializer

    def get_queryset(self):
        return Package.objects.filter(is_active=True)


class ClinicPurchaseRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsClinicAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PurchaseRequestCreateSerializer
        return PurchaseRequestSerializer

    def get_queryset(self):
        clinic = _clinic_for(self.request)
        return PurchaseRequest.objects.filter(clinic=clinic).select_related(
            "clinic", "package", "requested_by"
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["clinic"] = _clinic_for(self.request)
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            PurchaseRequestSerializer(obj).data, status=status.HTTP_201_CREATED
        )


class ClinicSubscriptionListView(generics.ListAPIView):
    permission_classes = [IsClinicAdmin]
    serializer_class = ClinicSubscriptionSerializer

    def get_queryset(self):
        return ClinicSubscription.objects.filter(
            clinic=_clinic_for(self.request)
        ).select_related("clinic", "package")


class ClinicPaymentListView(generics.ListAPIView):
    permission_classes = [IsClinicAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return Payment.objects.filter(clinic=_clinic_for(self.request)).select_related(
            "clinic", "recorded_by"
        )


class ClinicLedgerListView(generics.ListAPIView):
    permission_classes = [IsClinicAdmin]
    serializer_class = LedgerEntrySerializer

    def get_queryset(self):
        return LedgerEntry.objects.filter(
            clinic=_clinic_for(self.request)
        ).select_related("clinic", "created_by")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        clinic = _clinic_for(request)
        balance = str(clinic_ledger_balance(clinic))
        active_sub = active_subscription_summary(clinic)
        payment_summary = clinic_payment_summary(clinic)
        if isinstance(response.data, dict):
            response.data["ledger_balance"] = balance
            response.data["active_subscription"] = active_sub
            response.data["payment_summary"] = payment_summary
        else:
            response.data = {
                "results": response.data,
                "ledger_balance": balance,
                "active_subscription": active_sub,
                "payment_summary": payment_summary,
                "count": len(response.data),
                "next": None,
                "previous": None,
            }
        return response


def _clinic_doctors_qs(request):
    return (
        DoctorProfile.objects.filter(
            doctor_clinics__clinic=_clinic_for(request),
        )
        .select_related("user", "clinic")
        .prefetch_related("specialities", "subscriptions", "bank_accounts")
        .distinct()
    )


class ClinicSpecialityListView(generics.ListAPIView):
    permission_classes = [IsClinicAdmin]
    serializer_class = SpecialitySerializer

    def get_queryset(self):
        return Speciality.objects.filter(is_active=True).order_by("name")


class ClinicDoctorListView(generics.ListCreateAPIView):
    """Clinic-scoped doctor roster: list + create."""

    permission_classes = [IsClinicAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ClinicDoctorCreateSerializer
        return DoctorProfileSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["clinic"] = _clinic_for(self.request)
        return ctx

    def get_queryset(self):
        qs = _clinic_doctors_qs(self.request)
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
        return qs.distinct()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor = serializer.save()
        return Response(
            DoctorProfileSerializer(doctor, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ClinicDoctorDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Clinic-scoped doctor detail: retrieve, update, unlink (delete)."""

    permission_classes = [IsClinicAdmin]
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return _clinic_doctors_qs(self.request)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ClinicDoctorUpdateSerializer
        return ClinicDoctorDetailSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["clinic"] = _clinic_for(self.request)
        if self.request.method == "PATCH":
            ctx["doctor"] = self.get_object()
        return ctx

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        doctor = serializer.save()
        detail = ClinicDoctorDetailSerializer(
            doctor,
            context={"request": request, "clinic": _clinic_for(request)},
        )
        return Response(detail.data)

    def destroy(self, request, *args, **kwargs):
        doctor = self.get_object()
        clinic = _clinic_for(request)
        deleted, _ = DoctorClinic.objects.filter(doctor=doctor, clinic=clinic).delete()
        if not deleted:
            return Response(
                {"detail": "Doctor is not linked to this clinic."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClinicDoctorImportTemplateView(APIView):
    permission_classes = [IsClinicAdmin]

    def get(self, request):
        data = build_import_template_bytes()
        response = HttpResponse(
            data,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            'attachment; filename="clinic_doctors_import_template.xlsx"'
        )
        return response


class ClinicDoctorImportView(APIView):
    permission_classes = [IsClinicAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response(
                {"detail": "Upload a .xlsx or .csv file as 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        clinic = _clinic_for(request)
        result = import_doctors_for_clinic(clinic, uploaded)
        return Response(result, status=status.HTTP_200_OK)


def _clinic_appointments_qs(request):
    return Appointment.objects.filter(clinic=_clinic_for(request)).select_related(
        "patient", "doctor", "clinic"
    )


class ClinicAppointmentListView(generics.ListCreateAPIView):
    """Clinic-scoped appointments: list + create."""

    permission_classes = [IsClinicAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ClinicAppointmentCreateSerializer
        return AppointmentSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["clinic"] = _clinic_for(self.request)
        return ctx

    def get_queryset(self):
        qs = _clinic_appointments_qs(self.request)
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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save()
        return Response(
            AppointmentSerializer(appointment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ClinicAppointmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Clinic-scoped appointment detail: retrieve, update, delete."""

    permission_classes = [IsClinicAdmin]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ClinicAppointmentUpdateSerializer
        return AppointmentDetailSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["clinic"] = _clinic_for(self.request)
        return ctx

    def get_queryset(self):
        return _clinic_appointments_qs(self.request).prefetch_related("attachments")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save()
        return Response(
            AppointmentDetailSerializer(
                appointment, context={"request": request}
            ).data
        )
