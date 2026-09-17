from rest_framework import serializers

from catalog.models import DoctorProfile
from patients.models import PatientProfile

from .models import (
    Appointment,
    ClinicalNote,
    Prescription,
    PrescriptionItem,
    VisitAttachment,
)


class ClinicalNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalNote
        fields = (
            "id",
            "subjective",
            "objective",
            "assessment",
            "plan",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = (
            "id",
            "medicine_name",
            "dosage",
            "frequency",
            "duration",
            "instructions",
        )
        read_only_fields = ("id",)


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True)

    class Meta:
        model = Prescription
        fields = ("id", "notes", "items", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        prescription = Prescription.objects.create(**validated_data)
        for item_data in items_data:
            PrescriptionItem.objects.create(prescription=prescription, **item_data)
        return prescription

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        instance.notes = validated_data.get("notes", instance.notes)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PrescriptionItem.objects.create(prescription=instance, **item_data)
        return instance


class VisitAttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = VisitAttachment
        fields = (
            "id",
            "kind",
            "url",
            "original_name",
            "mime_type",
            "duration_seconds",
            "sent_via_whatsapp",
            "transcript_text",
            "summary_text",
            "summary_status",
            "summary_error",
            "created_at",
        )
        read_only_fields = fields

    def get_url(self, obj):
        # Relative /media/... so mobile clients can prefix EXPO_PUBLIC_API_URL.
        if not obj.file:
            return ""
        request = self.context.get("request")
        url = obj.file.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class VisitAttachmentSummaryUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitAttachment
        fields = ("summary_text",)

    def validate_summary_text(self, value):
        return (value or "").strip()

    def update(self, instance, validated_data):
        instance.summary_text = validated_data.get(
            "summary_text", instance.summary_text
        )
        instance.summary_status = VisitAttachment.SummaryStatus.READY
        instance.summary_error = ""
        instance.save(
            update_fields=["summary_text", "summary_status", "summary_error"]
        )
        return instance


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    patient_uuid = serializers.UUIDField(source="patient.uuid", read_only=True)
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    clinic_name = serializers.CharField(source="clinic.name", read_only=True, default=None)
    token_code = serializers.CharField(read_only=True)
    visit_duration_seconds = serializers.SerializerMethodField()
    attachment_count = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = (
            "id",
            "patient",
            "patient_uuid",
            "patient_name",
            "patient_phone",
            "doctor",
            "doctor_name",
            "clinic",
            "clinic_name",
            "scheduled_at",
            "token_date",
            "token_number",
            "token_code",
            "status",
            "notes",
            "rejection_reason",
            "visit_started_at",
            "visit_ended_at",
            "visit_duration_seconds",
            "attachment_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "created_at",
            "updated_at",
            "token_date",
            "token_number",
            "token_code",
            "visit_started_at",
            "visit_ended_at",
            "visit_duration_seconds",
            "attachment_count",
        )

    def get_visit_duration_seconds(self, obj):
        if not obj.visit_started_at:
            return None
        from django.utils import timezone

        end = obj.visit_ended_at or timezone.now()
        return max(0, int((end - obj.visit_started_at).total_seconds()))

    def get_attachment_count(self, obj):
        if hasattr(obj, "_attachment_count"):
            return obj._attachment_count
        return obj.attachments.count()


class AppointmentDetailSerializer(AppointmentSerializer):
    clinical_note = serializers.SerializerMethodField()
    prescription = serializers.SerializerMethodField()
    attachments = VisitAttachmentSerializer(many=True, read_only=True)

    class Meta(AppointmentSerializer.Meta):
        fields = AppointmentSerializer.Meta.fields + (
            "clinical_note",
            "prescription",
            "attachments",
        )

    def get_clinical_note(self, obj):
        try:
            return ClinicalNoteSerializer(obj.clinical_note).data
        except ClinicalNote.DoesNotExist:
            return None

    def get_prescription(self, obj):
        try:
            return PrescriptionSerializer(obj.prescription).data
        except Prescription.DoesNotExist:
            return None


class AppointmentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = (
            "patient",
            "doctor",
            "scheduled_at",
            "token_date",
            "token_number",
            "status",
            "notes",
            "rejection_reason",
        )

    def validate_doctor(self, value: DoctorProfile):
        if not value.is_active:
            raise serializers.ValidationError("Doctor is not active.")
        return value

    def validate_patient(self, value: PatientProfile):
        return value


class DoctorAppointmentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ("status", "rejection_reason")

    def validate_status(self, value):
        allowed = {
            Appointment.Status.COMPLETED,
            Appointment.Status.REJECTED,
        }
        if value not in allowed:
            raise serializers.ValidationError(
                "Doctors can only set status to completed or rejected."
            )
        return value


class DoctorBookSerializer(serializers.Serializer):
    patient_uuid = serializers.UUIDField(required=False)
    phone = serializers.CharField(required=False, max_length=20)
    name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    clinic_id = serializers.IntegerField()
    token_date = serializers.DateField()
    slot_time = serializers.TimeField()
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate_phone(self, value):
        from patients.serializers import normalize_phone

        phone = normalize_phone(value)
        if len(phone) < 10:
            raise serializers.ValidationError("Enter a valid phone number.")
        return phone

    def validate(self, attrs):
        from appointments.services import (
            generate_slots_for_windows,
            pakistan_now,
            pakistan_today,
            upcoming_available_dates,
        )
        from catalog.models import Clinic, DoctorClinic
        from patients.serializers import clean_name

        doctor = self.context.get("doctor")
        if doctor is None or not doctor.is_active:
            raise serializers.ValidationError("Doctor not found or inactive.")

        patient_uuid = attrs.get("patient_uuid")
        phone = attrs.get("phone")
        if not patient_uuid and not phone:
            raise serializers.ValidationError(
                "Provide patient_uuid or phone to identify the patient."
            )
        if patient_uuid and phone:
            raise serializers.ValidationError(
                "Provide either patient_uuid or phone, not both."
            )

        if patient_uuid:
            patient = PatientProfile.objects.filter(uuid=patient_uuid).first()
            if not patient:
                raise serializers.ValidationError(
                    {"patient_uuid": "Patient not found."}
                )
            attrs["patient"] = patient
            attrs["create_patient"] = False
        else:
            patient = PatientProfile.objects.filter(phone=phone).first()
            if patient:
                attrs["patient"] = patient
                attrs["create_patient"] = False
            else:
                name_in = clean_name(attrs.get("name") or "")
                if not name_in:
                    raise serializers.ValidationError(
                        {"name": "Full name is required for new patients."}
                    )
                attrs["patient"] = None
                attrs["create_patient"] = True
                attrs["new_patient_name"] = name_in
                attrs["new_patient_phone"] = phone

        clinic = Clinic.objects.filter(pk=attrs["clinic_id"], is_active=True).first()
        if not clinic:
            raise serializers.ValidationError({"clinic_id": "Clinic not found."})
        if not DoctorClinic.objects.filter(doctor=doctor, clinic=clinic).exists():
            raise serializers.ValidationError(
                {"clinic_id": "You are not linked to this clinic."}
            )

        token_date = attrs["token_date"]
        options = upcoming_available_dates(doctor, clinic=clinic)
        allowed = {o["date"] for o in options}
        if token_date.isoformat() not in allowed:
            raise serializers.ValidationError(
                {"token_date": "Selected date is not available at this clinic."}
            )
        match = next(o for o in options if o["date"] == token_date.isoformat())
        attrs["start"] = match["start"]
        attrs["clinic"] = clinic
        attrs["windows"] = match.get("windows") or [
            {"start": match["start"], "end": match["end"]}
        ]

        slot_time = attrs["slot_time"]
        valid = generate_slots_for_windows(attrs["windows"], doctor.session_time)
        if slot_time not in valid:
            raise serializers.ValidationError(
                {"slot_time": "Selected time is not available for this clinic."}
            )

        booked = set(match.get("booked_times") or [])
        slot_key = slot_time.strftime("%H:%M:%S")
        if slot_key in booked:
            raise serializers.ValidationError(
                {"slot_time": "This time slot is already booked."}
            )

        if token_date == pakistan_today():
            now = pakistan_now().time()
            if slot_time <= now:
                raise serializers.ValidationError(
                    {"slot_time": "Selected time has already passed."}
                )

        return attrs
