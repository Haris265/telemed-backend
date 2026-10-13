from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from accounts.models import ClinicAdminProfile
from appointments.models import Appointment
from catalog.models import Clinic, DoctorClinic, DoctorProfile
from catalog.serializers import DoctorProfileSerializer

from .clinic_doctors import build_detail_payload, clinic_link_for
from .models import ClinicSubscription, LedgerEntry, Package, Payment, PurchaseRequest
from .services import (
    active_subscription_summary,
    add_ledger_adjustment,
    clinic_ledger_balance,
    clinic_payment_summary,
    confirm_cash_purchase,
    reject_purchase_request,
)

User = get_user_model()


class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = (
            "id",
            "uuid",
            "name",
            "code",
            "description",
            "price",
            "duration_days",
            "max_doctors",
            "max_patients",
            "features",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")


class ClinicBillingSerializer(serializers.ModelSerializer):
    has_active_package = serializers.SerializerMethodField()
    ledger_balance = serializers.SerializerMethodField()
    clinic_admin_username = serializers.SerializerMethodField()
    active_subscription = serializers.SerializerMethodField()
    payment_summary = serializers.SerializerMethodField()

    class Meta:
        model = Clinic
        fields = (
            "id",
            "name",
            "address",
            "city",
            "area",
            "phone",
            "billing_email",
            "owner_name",
            "latitude",
            "longitude",
            "is_active",
            "has_active_package",
            "ledger_balance",
            "clinic_admin_username",
            "active_subscription",
            "payment_summary",
            "created_at",
        )
        read_only_fields = (
            "created_at",
            "has_active_package",
            "ledger_balance",
            "clinic_admin_username",
            "active_subscription",
            "payment_summary",
        )

    def get_has_active_package(self, obj):
        return obj.has_active_package()

    def get_ledger_balance(self, obj):
        return str(clinic_ledger_balance(obj))

    def get_clinic_admin_username(self, obj):
        admin = obj.clinic_admins.select_related("user").first()
        return admin.user.username if admin else None

    def get_active_subscription(self, obj):
        return active_subscription_summary(obj)

    def get_payment_summary(self, obj):
        return clinic_payment_summary(obj)


class ClinicAdminCreateSerializer(serializers.Serializer):
    clinic_id = serializers.IntegerField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_clinic_id(self, value):
        if not Clinic.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Clinic not found.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def create(self, validated_data):
        clinic = Clinic.objects.get(pk=validated_data["clinic_id"])
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            email=validated_data.get("email") or "",
            first_name=validated_data.get("first_name") or "",
            last_name=validated_data.get("last_name") or "",
            role=User.Role.CLINIC_ADMIN,
        )
        profile = ClinicAdminProfile.objects.create(user=user, clinic=clinic)
        return profile


class ClinicAdminProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)

    class Meta:
        model = ClinicAdminProfile
        fields = ("id", "username", "email", "clinic", "clinic_name", "created_at")


class ClinicSubscriptionSerializer(serializers.ModelSerializer):
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True)
    package_code = serializers.CharField(source="package.code", read_only=True)
    duration_days = serializers.IntegerField(
        source="package.duration_days", read_only=True
    )
    is_currently_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = ClinicSubscription
        fields = (
            "id",
            "uuid",
            "clinic",
            "clinic_name",
            "package",
            "package_name",
            "package_code",
            "duration_days",
            "start_date",
            "end_date",
            "amount_paid",
            "status",
            "is_active",
            "is_currently_valid",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "created_at",
            "updated_at",
            "is_currently_valid",
            "duration_days",
        )


class PurchaseRequestSerializer(serializers.ModelSerializer):
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True)
    package_price = serializers.DecimalField(
        source="package.price", max_digits=12, decimal_places=2, read_only=True
    )
    requested_by_username = serializers.CharField(
        source="requested_by.username", read_only=True, default=None
    )

    class Meta:
        model = PurchaseRequest
        fields = (
            "id",
            "uuid",
            "clinic",
            "clinic_name",
            "package",
            "package_name",
            "package_price",
            "requested_by",
            "requested_by_username",
            "status",
            "notes",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "uuid",
            "clinic",
            "requested_by",
            "status",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        )


class PurchaseRequestCreateSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_package_id(self, value):
        try:
            package = Package.objects.get(pk=value, is_active=True)
        except Package.DoesNotExist:
            raise serializers.ValidationError("Active package not found.")
        self.context["package"] = package
        return value

    def create(self, validated_data):
        clinic = self.context["clinic"]
        user = self.context["request"].user
        package = self.context["package"]
        pending = PurchaseRequest.objects.filter(
            clinic=clinic,
            package=package,
            status=PurchaseRequest.Status.PENDING,
        ).exists()
        if pending:
            raise serializers.ValidationError(
                {"package_id": "A pending request already exists for this package."}
            )
        return PurchaseRequest.objects.create(
            clinic=clinic,
            package=package,
            requested_by=user,
            notes=validated_data.get("notes") or "",
        )


class ApprovePurchaseSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    start_date = serializers.DateField(required=False, allow_null=True)

    def save(self, **kwargs):
        request_obj: PurchaseRequest = self.context["purchase_request"]
        amount = self.validated_data.get("amount")
        if amount is None:
            amount = request_obj.package.price
        payment, subscription = confirm_cash_purchase(
            clinic=request_obj.clinic,
            package=request_obj.package,
            amount=Decimal(amount),
            recorded_by=self.context["request"].user,
            purchase_request=request_obj,
            notes=self.validated_data.get("notes") or "",
            start_date=self.validated_data.get("start_date"),
        )
        return {"payment": payment, "subscription": subscription}


class RejectPurchaseSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def save(self, **kwargs):
        return reject_purchase_request(
            purchase_request=self.context["purchase_request"],
            reviewed_by=self.context["request"].user,
            notes=self.validated_data.get("notes") or "",
        )


class DirectAssignSerializer(serializers.Serializer):
    clinic_id = serializers.IntegerField()
    package_id = serializers.IntegerField()
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    start_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        try:
            clinic = Clinic.objects.get(pk=attrs["clinic_id"])
        except Clinic.DoesNotExist:
            raise serializers.ValidationError({"clinic_id": "Clinic not found."})
        try:
            package = Package.objects.get(pk=attrs["package_id"], is_active=True)
        except Package.DoesNotExist:
            raise serializers.ValidationError({"package_id": "Active package not found."})
        attrs["clinic"] = clinic
        attrs["package"] = package
        return attrs

    def save(self, **kwargs):
        amount = self.validated_data.get("amount")
        if amount is None:
            amount = self.validated_data["package"].price
        payment, subscription = confirm_cash_purchase(
            clinic=self.validated_data["clinic"],
            package=self.validated_data["package"],
            amount=Decimal(amount),
            recorded_by=self.context["request"].user,
            purchase_request=None,
            notes=self.validated_data.get("notes") or "",
            start_date=self.validated_data.get("start_date"),
        )
        return {"payment": payment, "subscription": subscription}


class PaymentSerializer(serializers.ModelSerializer):
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    recorded_by_username = serializers.CharField(
        source="recorded_by.username", read_only=True, default=None
    )

    class Meta:
        model = Payment
        fields = (
            "id",
            "uuid",
            "clinic",
            "clinic_name",
            "amount",
            "method",
            "status",
            "purchase_request",
            "subscription",
            "recorded_by",
            "recorded_by_username",
            "paid_at",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class LedgerEntrySerializer(serializers.ModelSerializer):
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )

    class Meta:
        model = LedgerEntry
        fields = (
            "id",
            "uuid",
            "clinic",
            "clinic_name",
            "entry_type",
            "amount",
            "balance_after",
            "payment",
            "subscription",
            "notes",
            "created_by",
            "created_by_username",
            "created_at",
        )
        read_only_fields = fields


class LedgerAdjustmentSerializer(serializers.Serializer):
    clinic_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_clinic_id(self, value):
        if not Clinic.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Clinic not found.")
        return value

    def save(self, **kwargs):
        clinic = Clinic.objects.get(pk=self.validated_data["clinic_id"])
        return add_ledger_adjustment(
            clinic=clinic,
            amount=Decimal(self.validated_data["amount"]),
            created_by=self.context["request"].user,
            notes=self.validated_data.get("notes") or "",
        )


class ClinicDoctorDetailSerializer(DoctorProfileSerializer):
    """Profile plus clinic-scoped schedule, visits, and commission split."""

    clinic_link = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    upcoming_slots = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    patients = serializers.SerializerMethodField()
    appointments = serializers.SerializerMethodField()

    class Meta(DoctorProfileSerializer.Meta):
        fields = DoctorProfileSerializer.Meta.fields + (
            "clinic_link",
            "availability",
            "upcoming_slots",
            "stats",
            "patients",
            "appointments",
        )

    def _payload(self, obj: DoctorProfile) -> dict:
        if not hasattr(self, "_payload_cache"):
            self._payload_cache = {}
        key = obj.pk
        if key not in self._payload_cache:
            clinic = self.context["clinic"]
            self._payload_cache[key] = build_detail_payload(obj, clinic)
        return self._payload_cache[key]

    def get_clinic_link(self, obj):
        return self._payload(obj)["clinic_link"]

    def get_availability(self, obj):
        return self._payload(obj)["availability"]

    def get_upcoming_slots(self, obj):
        return self._payload(obj)["upcoming_slots"]

    def get_stats(self, obj):
        return self._payload(obj)["stats"]

    def get_patients(self, obj):
        return self._payload(obj)["patients"]

    def get_appointments(self, obj):
        return self._payload(obj)["appointments"]


class ClinicDoctorUpdateSerializer(serializers.Serializer):
    commission_type = serializers.ChoiceField(
        choices=DoctorClinic.CommissionType.choices, required=False
    )
    commission_value = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )
    consultation_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )

    def validate(self, attrs):
        ctype = attrs.get("commission_type")
        cval = attrs.get("commission_value")
        doctor: DoctorProfile = self.context["doctor"]
        clinic: Clinic = self.context["clinic"]
        link = clinic_link_for(doctor, clinic)
        if link is None:
            raise serializers.ValidationError("Doctor is not linked to this clinic.")
        effective_type = ctype or link.commission_type
        effective_val = cval if cval is not None else link.commission_value
        if effective_type == DoctorClinic.CommissionType.PERCENTAGE:
            if effective_val > Decimal("100"):
                raise serializers.ValidationError(
                    {"commission_value": "Percentage must be between 0 and 100."}
                )
        self.context["link"] = link
        return attrs

    def save(self, **kwargs):
        doctor: DoctorProfile = self.context["doctor"]
        clinic: Clinic = self.context["clinic"]
        link: DoctorClinic = self.context["link"]
        changed = False
        if "commission_type" in self.validated_data:
            link.commission_type = self.validated_data["commission_type"]
            changed = True
        if "commission_value" in self.validated_data:
            link.commission_value = self.validated_data["commission_value"]
            changed = True
        if changed:
            link.commission_updated_at = timezone.now()
            link.save(
                update_fields=[
                    "commission_type",
                    "commission_value",
                    "commission_updated_at",
                ]
            )
        if "consultation_fee" in self.validated_data:
            fee = self.validated_data["consultation_fee"]
            doctor.consultation_fee = fee
            doctor.save(update_fields=["consultation_fee"])
            # Keep upcoming unpaid bookings aligned with the new listed fee.
            Appointment.objects.filter(
                doctor=doctor,
                clinic=clinic,
                status=Appointment.Status.UPCOMING,
            ).exclude(
                payment_status=Appointment.PaymentStatus.PAID,
            ).update(payment_amount_expected=fee)
        doctor.refresh_from_db()
        return doctor
