from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import (
    Clinic,
    DoctorAvailability,
    DoctorClinic,
    DoctorProfile,
    DoctorSubscription,
    Speciality,
)

# Default map pin (Karachi center) when doctor creates a clinic without GPS.
DEFAULT_CLINIC_LAT = Decimal("24.860700")
DEFAULT_CLINIC_LNG = Decimal("67.001100")

User = get_user_model()


class SpecialitySerializer(serializers.ModelSerializer):
    display_icon = serializers.CharField(read_only=True)

    class Meta:
        model = Speciality
        fields = (
            "id",
            "name",
            "icon",
            "icon_url",
            "display_icon",
            "is_active",
            "created_at",
        )
        read_only_fields = ("created_at",)


class ClinicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clinic
        fields = (
            "id",
            "name",
            "address",
            "city",
            "area",
            "phone",
            "latitude",
            "longitude",
            "is_active",
            "created_at",
        )
        read_only_fields = ("created_at",)

    def validate_latitude(self, value):
        if value < -90 or value > 90:
            raise serializers.ValidationError("latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        if value < -180 or value > 180:
            raise serializers.ValidationError("longitude must be between -180 and 180.")
        return value


class DoctorOnboardingSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    speciality_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
    session_time = serializers.IntegerField(min_value=5, max_value=240)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, write_only=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value.lower()

    def validate_speciality_ids(self, value):
        qs = Speciality.objects.filter(id__in=value, is_active=True)
        if qs.count() != len(set(value)):
            raise serializers.ValidationError("One or more specialities are invalid.")
        return list(set(value))

    @transaction.atomic
    def create(self, validated_data):
        speciality_ids = validated_data.pop("speciality_ids")
        password = validated_data.pop("password")
        email = validated_data.pop("email")
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            role=User.Role.DOCTOR,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
        )
        doctor = DoctorProfile.objects.create(user=user, **validated_data)
        doctor.specialities.set(speciality_ids)
        return doctor


class DoctorProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    specialities = SpecialitySerializer(many=True, read_only=True)
    speciality_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )
    clinic_name = serializers.CharField(
        source="clinic.name",
        read_only=True,
        allow_null=True,
        required=False,
    )
    full_name = serializers.CharField(read_only=True)
    has_active_subscription = serializers.SerializerMethodField()
    subscription_status = serializers.CharField(read_only=True)

    class Meta:
        model = DoctorProfile
        fields = (
            "id",
            "uuid",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "specialities",
            "speciality_ids",
            "clinic",
            "clinic_name",
            "session_time",
            "is_active",
            "has_active_subscription",
            "subscription_status",
            "created_at",
        )
        read_only_fields = ("uuid", "created_at")

    def get_has_active_subscription(self, obj):
        return obj.has_active_subscription()

    def validate_speciality_ids(self, value):
        if not value:
            raise serializers.ValidationError("Select at least one speciality.")
        existing = set(Speciality.objects.filter(id__in=value).values_list("id", flat=True))
        if existing != set(value):
            raise serializers.ValidationError("One or more specialities are invalid.")
        return list(existing)

    def update(self, instance, validated_data):
        speciality_ids = validated_data.pop("speciality_ids", None)
        instance = super().update(instance, validated_data)
        if speciality_ids is not None:
            instance.specialities.set(speciality_ids)
        return instance


class DoctorSubscriptionSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    doctor_uuid = serializers.UUIDField(source="doctor.uuid", read_only=True)
    doctor_email = serializers.EmailField(source="doctor.user.email", read_only=True)
    is_currently_valid = serializers.BooleanField(read_only=True)
    payment_method = serializers.ChoiceField(
        choices=DoctorSubscription.PaymentMethod.choices,
        default=DoctorSubscription.PaymentMethod.CASH,
    )

    class Meta:
        model = DoctorSubscription
        fields = (
            "id",
            "uuid",
            "doctor",
            "doctor_uuid",
            "doctor_name",
            "doctor_email",
            "amount",
            "payment_method",
            "start_date",
            "end_date",
            "is_active",
            "is_currently_valid",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("uuid", "created_at", "updated_at")

    def validate(self, attrs):
        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "end_date must be on or after start_date."})
        payment = attrs.get("payment_method", DoctorSubscription.PaymentMethod.CASH)
        if payment != DoctorSubscription.PaymentMethod.CASH:
            raise serializers.ValidationError({"payment_method": "Only cash payments are supported."})
        return attrs

    def create(self, validated_data):
        validated_data["payment_method"] = DoctorSubscription.PaymentMethod.CASH
        subscription = super().create(validated_data)
        # Cash subscription received → keep doctor active
        doctor = subscription.doctor
        if not doctor.is_active:
            doctor.is_active = True
            doctor.save(update_fields=["is_active"])
        return subscription


class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)
    clinic_name = serializers.CharField(source="clinic.name", read_only=True, default=None)

    class Meta:
        model = DoctorAvailability
        fields = (
            "id",
            "clinic",
            "clinic_name",
            "weekday",
            "weekday_display",
            "start_time",
            "end_time",
            "is_active",
            "created_at",
        )
        read_only_fields = ("created_at",)

    def validate(self, attrs):
        start = attrs.get("start_time") or getattr(self.instance, "start_time", None)
        end = attrs.get("end_time") or getattr(self.instance, "end_time", None)
        # Midnight (00:00) means end of day, so 09:00–00:00 is valid.
        if start and end and end != time(0, 0) and start >= end:
            raise serializers.ValidationError("end_time must be after start_time.")
        return attrs


class DoctorClinicSerializer(serializers.ModelSerializer):
    clinic = ClinicSerializer(read_only=True)
    schedule_count = serializers.SerializerMethodField()

    class Meta:
        model = DoctorClinic
        fields = (
            "id",
            "clinic",
            "is_primary",
            "schedule_count",
            "created_at",
        )
        read_only_fields = ("created_at",)

    def get_schedule_count(self, obj):
        return obj.clinic.availabilities.filter(doctor=obj.doctor, is_active=True).count()


class DoctorClinicCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    address = serializers.CharField(max_length=300)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    area = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, default=DEFAULT_CLINIC_LAT
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, default=DEFAULT_CLINIC_LNG
    )
    is_primary = serializers.BooleanField(required=False, default=False)

    def validate_latitude(self, value):
        value = Decimal(str(value))
        if value < Decimal("-90") or value > Decimal("90"):
            raise serializers.ValidationError("latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        value = Decimal(str(value))
        if value < Decimal("-180") or value > Decimal("180"):
            raise serializers.ValidationError("longitude must be between -180 and 180.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        doctor: DoctorProfile = self.context["doctor"]
        is_primary = validated_data.pop("is_primary", False)
        clinic = Clinic.objects.create(**validated_data)

        if is_primary or not doctor.doctor_clinics.exists():
            doctor.doctor_clinics.filter(is_primary=True).update(is_primary=False)
            is_primary = True
            doctor.clinic = clinic
            doctor.save(update_fields=["clinic"])

        link = DoctorClinic.objects.create(
            doctor=doctor,
            clinic=clinic,
            is_primary=is_primary,
        )
        return link


class DoctorClinicUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    address = serializers.CharField(max_length=300, required=False)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    area = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    is_active = serializers.BooleanField(required=False)
    is_primary = serializers.BooleanField(required=False)

    def validate_latitude(self, value):
        value = Decimal(str(value))
        if value < Decimal("-90") or value > Decimal("90"):
            raise serializers.ValidationError("latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        value = Decimal(str(value))
        if value < Decimal("-180") or value > Decimal("180"):
            raise serializers.ValidationError("longitude must be between -180 and 180.")
        return value

    @transaction.atomic
    def update(self, instance: DoctorClinic, validated_data):
        clinic = instance.clinic
        clinic_fields = (
            "name",
            "address",
            "city",
            "area",
            "phone",
            "latitude",
            "longitude",
            "is_active",
        )
        for field in clinic_fields:
            if field in validated_data:
                setattr(clinic, field, validated_data[field])
        clinic.save()

        if "is_primary" in validated_data and validated_data["is_primary"]:
            instance.doctor.doctor_clinics.exclude(pk=instance.pk).update(is_primary=False)
            instance.is_primary = True
            instance.doctor.clinic = clinic
            instance.doctor.save(update_fields=["clinic"])
            instance.save(update_fields=["is_primary"])
        elif "is_primary" in validated_data and not validated_data["is_primary"]:
            instance.is_primary = False
            instance.save(update_fields=["is_primary"])

        return instance
