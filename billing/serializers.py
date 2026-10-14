from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import ClinicAdminProfile
from appointments.models import Appointment
from catalog.models import Clinic, DoctorClinic, DoctorProfile, Speciality
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


def create_doctor_for_clinic(
    *,
    clinic: Clinic,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    speciality_ids: list[int],
    session_time: int,
    consultation_fee=None,
) -> DoctorProfile:
    """Create doctor user + profile and link to clinic."""
    with transaction.atomic():
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=User.Role.DOCTOR,
            first_name=first_name,
            last_name=last_name,
        )
        fee = (
            Decimal(consultation_fee)
            if consultation_fee is not None
            else Decimal("0")
        )
        doctor = DoctorProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            session_time=session_time,
            consultation_fee=fee,
            clinic=clinic,
        )
        doctor.specialities.set(speciality_ids)
        DoctorClinic.objects.get_or_create(
            doctor=doctor,
            clinic=clinic,
            defaults={"is_primary": True},
        )
        return doctor


class ClinicDoctorCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    speciality_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
    session_time = serializers.IntegerField(min_value=5, max_value=240)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, write_only=True)
    consultation_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
    )

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        if User.objects.filter(username__iexact=email).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return email

    def validate_speciality_ids(self, value):
        qs = Speciality.objects.filter(id__in=value, is_active=True)
        if qs.count() != len(set(value)):
            raise serializers.ValidationError("One or more specialities are invalid.")
        return list(set(value))

    def create(self, validated_data):
        clinic: Clinic = self.context["clinic"]
        return create_doctor_for_clinic(
            clinic=clinic,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            email=validated_data["email"],
            password=validated_data["password"],
            speciality_ids=validated_data["speciality_ids"],
            session_time=validated_data["session_time"],
            consultation_fee=validated_data.get("consultation_fee"),
        )


class ClinicDoctorUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    speciality_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
    )
    session_time = serializers.IntegerField(min_value=5, max_value=240, required=False)
    is_active = serializers.BooleanField(required=False)
    commission_type = serializers.ChoiceField(
        choices=DoctorClinic.CommissionType.choices, required=False
    )
    commission_value = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )
    discounted_commission_type = serializers.ChoiceField(
        choices=DoctorClinic.CommissionType.choices, required=False
    )
    discounted_commission_value = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )
    consultation_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )

    def validate_speciality_ids(self, value):
        qs = Speciality.objects.filter(id__in=value, is_active=True)
        if qs.count() != len(set(value)):
            raise serializers.ValidationError("One or more specialities are invalid.")
        return list(set(value))

    def validate(self, attrs):
        ctype = attrs.get("commission_type")
        cval = attrs.get("commission_value")
        dctype = attrs.get("discounted_commission_type")
        dcval = attrs.get("discounted_commission_value")
        doctor: DoctorProfile = self.context["doctor"]
        clinic: Clinic = self.context["clinic"]
        link = clinic_link_for(doctor, clinic)
        if link is None:
            raise serializers.ValidationError("Doctor is not linked to this clinic.")
        if ctype is not None or cval is not None:
            effective_type = ctype or link.commission_type
            effective_val = cval if cval is not None else link.commission_value
            if effective_type == DoctorClinic.CommissionType.PERCENTAGE:
                if effective_val > Decimal("100"):
                    raise serializers.ValidationError(
                        {"commission_value": "Percentage must be between 0 and 100."}
                    )
        if dctype is not None or dcval is not None:
            effective_dtype = dctype or link.discounted_commission_type
            effective_dval = (
                dcval if dcval is not None else link.discounted_commission_value
            )
            if effective_dtype == DoctorClinic.CommissionType.PERCENTAGE:
                if effective_dval > Decimal("100"):
                    raise serializers.ValidationError(
                        {
                            "discounted_commission_value": (
                                "Percentage must be between 0 and 100."
                            )
                        }
                    )
        self.context["link"] = link
        return attrs

    def save(self, **kwargs):
        doctor: DoctorProfile = self.context["doctor"]
        clinic: Clinic = self.context["clinic"]
        link: DoctorClinic = self.context["link"]
        data = self.validated_data

        profile_fields = []
        if "first_name" in data:
            doctor.first_name = data["first_name"]
            doctor.user.first_name = data["first_name"]
            profile_fields.append("first_name")
        if "last_name" in data:
            doctor.last_name = data["last_name"]
            doctor.user.last_name = data["last_name"]
            profile_fields.append("last_name")
        if "session_time" in data:
            doctor.session_time = data["session_time"]
            profile_fields.append("session_time")
        if "is_active" in data:
            doctor.is_active = data["is_active"]
            profile_fields.append("is_active")
        if "consultation_fee" in data:
            fee = data["consultation_fee"]
            doctor.consultation_fee = fee
            profile_fields.append("consultation_fee")
            Appointment.objects.filter(
                doctor=doctor,
                clinic=clinic,
                status=Appointment.Status.UPCOMING,
            ).exclude(
                payment_status=Appointment.PaymentStatus.PAID,
            ).update(payment_amount_expected=fee)

        if profile_fields:
            doctor.save(update_fields=profile_fields)
            if "first_name" in data or "last_name" in data:
                doctor.user.save(update_fields=["first_name", "last_name"])

        if "speciality_ids" in data:
            doctor.specialities.set(data["speciality_ids"])

        changed = False
        update_fields: list[str] = []
        if "commission_type" in data:
            link.commission_type = data["commission_type"]
            changed = True
            update_fields.append("commission_type")
        if "commission_value" in data:
            link.commission_value = data["commission_value"]
            changed = True
            update_fields.append("commission_value")
        if changed:
            link.commission_updated_at = timezone.now()
            update_fields.append("commission_updated_at")

        dchanged = False
        if "discounted_commission_type" in data:
            link.discounted_commission_type = data["discounted_commission_type"]
            dchanged = True
            update_fields.append("discounted_commission_type")
        if "discounted_commission_value" in data:
            link.discounted_commission_value = data["discounted_commission_value"]
            dchanged = True
            update_fields.append("discounted_commission_value")
        if dchanged:
            link.discounted_commission_updated_at = timezone.now()
            update_fields.append("discounted_commission_updated_at")

        if update_fields:
            link.save(update_fields=update_fields)
        doctor.refresh_from_db()
        return doctor


class ClinicAppointmentCreateSerializer(serializers.Serializer):
    patient_name = serializers.CharField(max_length=150)
    patient_phone = serializers.CharField(max_length=20)
    doctor = serializers.IntegerField()
    token_date = serializers.DateField()
    slot_time = serializers.TimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    patient_type = serializers.ChoiceField(
        choices=Appointment.PatientType.choices,
        required=False,
        default=Appointment.PatientType.NORMAL,
    )
    jamat_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )

    def validate_patient_phone(self, value):
        from patients.serializers import normalize_phone

        phone = normalize_phone(value)
        if len(phone) < 10:
            raise serializers.ValidationError("Enter a valid phone number.")
        return phone

    def validate_patient_name(self, value):
        from patients.serializers import clean_name

        name = clean_name(value)
        if not name:
            raise serializers.ValidationError("Enter a valid patient name.")
        return name

    def validate_doctor(self, value):
        clinic: Clinic = self.context["clinic"]
        doctor = DoctorProfile.objects.filter(pk=value, is_active=True).first()
        if not doctor:
            raise serializers.ValidationError("Doctor not found or inactive.")
        if not DoctorClinic.objects.filter(doctor=doctor, clinic=clinic).exists():
            raise serializers.ValidationError("Doctor is not linked to this clinic.")
        return doctor

    def validate(self, attrs):
        patient_type = attrs.get("patient_type") or Appointment.PatientType.NORMAL
        jamat = (attrs.get("jamat_name") or "").strip()
        if patient_type == Appointment.PatientType.DISCOUNTED and not jamat:
            raise serializers.ValidationError(
                {"jamat_name": "Jamat / community name is required for discounted patients."}
            )
        attrs["patient_type"] = patient_type
        attrs["jamat_name"] = (
            jamat if patient_type == Appointment.PatientType.DISCOUNTED else ""
        )
        return attrs

    def create(self, validated_data):
        from appointments.services import book_token
        from patients.models import PatientProfile

        clinic: Clinic = self.context["clinic"]
        phone = validated_data["patient_phone"]
        name = validated_data["patient_name"]
        doctor: DoctorProfile = validated_data["doctor"]
        token_date = validated_data["token_date"]
        slot_time = validated_data.get("slot_time")
        notes = (validated_data.get("notes") or "").strip() or "Booked by clinic"
        patient_type = validated_data["patient_type"]
        jamat_name = validated_data.get("jamat_name") or ""

        patient = PatientProfile.objects.filter(phone=phone).first()
        if patient:
            if name and patient.name != name:
                patient.name = name
                patient.save(update_fields=["name"])
        else:
            patient = PatientProfile.objects.create(
                phone=phone,
                name=name,
                is_verified=True,
            )

        try:
            appointment = book_token(
                patient,
                doctor,
                token_date,
                slot_time=slot_time,
                clinic=clinic,
                notes=notes,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

        if (
            patient_type != Appointment.PatientType.NORMAL
            or jamat_name
        ):
            appointment.patient_type = patient_type
            appointment.jamat_name = jamat_name
            appointment.save(update_fields=["patient_type", "jamat_name"])
        return appointment


class ClinicAppointmentUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=Appointment.Status.choices, required=False
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    doctor = serializers.IntegerField(required=False)
    token_date = serializers.DateField(required=False)
    scheduled_at = serializers.DateTimeField(required=False)
    patient_type = serializers.ChoiceField(
        choices=Appointment.PatientType.choices, required=False
    )
    jamat_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )

    def validate_doctor(self, value):
        clinic: Clinic = self.context["clinic"]
        doctor = DoctorProfile.objects.filter(pk=value, is_active=True).first()
        if not doctor:
            raise serializers.ValidationError("Doctor not found or inactive.")
        if not DoctorClinic.objects.filter(doctor=doctor, clinic=clinic).exists():
            raise serializers.ValidationError("Doctor is not linked to this clinic.")
        return doctor

    def validate(self, attrs):
        instance: Appointment = self.instance
        patient_type = attrs.get("patient_type", instance.patient_type)
        if "jamat_name" in attrs:
            jamat = (attrs.get("jamat_name") or "").strip()
        else:
            jamat = (instance.jamat_name or "").strip()
        if patient_type == Appointment.PatientType.DISCOUNTED and not jamat:
            raise serializers.ValidationError(
                {"jamat_name": "Jamat / community name is required for discounted patients."}
            )
        if "patient_type" in attrs or "jamat_name" in attrs:
            attrs["patient_type"] = patient_type
            attrs["jamat_name"] = (
                jamat if patient_type == Appointment.PatientType.DISCOUNTED else ""
            )
        return attrs

    def update(self, instance: Appointment, validated_data):
        from django.db.models import Max

        doctor = validated_data.get("doctor", instance.doctor)
        token_date = validated_data.get("token_date", instance.token_date)
        doctor_changed = doctor.pk != instance.doctor_id
        date_changed = token_date != instance.token_date

        if "status" in validated_data:
            instance.status = validated_data["status"]
        if "notes" in validated_data:
            instance.notes = validated_data["notes"]
        if "scheduled_at" in validated_data:
            instance.scheduled_at = validated_data["scheduled_at"]
        if "patient_type" in validated_data:
            instance.patient_type = validated_data["patient_type"]
        if "jamat_name" in validated_data:
            instance.jamat_name = validated_data["jamat_name"]

        if doctor_changed or date_changed:
            locked = (
                Appointment.objects.filter(doctor=doctor, token_date=token_date)
                .exclude(pk=instance.pk)
                .aggregate(m=Max("token_number"))
            )
            instance.token_number = (locked["m"] or 0) + 1
            instance.doctor = doctor
            instance.token_date = token_date

        instance.save()
        return instance
