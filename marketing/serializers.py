from rest_framework import serializers

from catalog.models import DoctorProfile

from .models import (
    CampaignRecipient,
    MarketingCampaign,
    MarketingSubscription,
    MessageTemplate,
)


class MarketingSubscriptionSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    doctor_uuid = serializers.UUIDField(source="doctor.uuid", read_only=True)
    doctor_email = serializers.EmailField(source="doctor.user.email", read_only=True)
    is_currently_valid = serializers.BooleanField(read_only=True)
    payment_method = serializers.ChoiceField(
        choices=MarketingSubscription.PaymentMethod.choices,
        default=MarketingSubscription.PaymentMethod.CASH,
    )

    class Meta:
        model = MarketingSubscription
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
        read_only_fields = ("uuid", "created_at", "updated_at", "is_currently_valid")

    def validate_payment_method(self, value):
        if value != MarketingSubscription.PaymentMethod.CASH:
            raise serializers.ValidationError("Only cash payment is supported.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )
        return attrs


class MessageTemplateSerializer(serializers.ModelSerializer):
    header_image_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageTemplate
        fields = (
            "id",
            "name",
            "body",
            "header_image",
            "header_image_url",
            "meta_template_name",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "header_image_url")
        extra_kwargs = {"header_image": {"required": False, "allow_null": True}}

    def get_header_image_url(self, obj):
        if not obj.header_image:
            return ""
        request = self.context.get("request")
        url = obj.header_image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_body(self, value):
        return (value or "").strip()


class CampaignRecipientSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(
        source="patient.name", read_only=True, default=""
    )

    class Meta:
        model = CampaignRecipient
        fields = (
            "id",
            "phone",
            "patient",
            "patient_name",
            "status",
            "error",
            "sent_at",
        )
        read_only_fields = fields


class MarketingCampaignSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    recipient_counts = serializers.SerializerMethodField()

    class Meta:
        model = MarketingCampaign
        fields = (
            "id",
            "name",
            "template",
            "template_name",
            "filter_json",
            "status",
            "recipient_counts",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
        )
        read_only_fields = (
            "id",
            "status",
            "template_name",
            "recipient_counts",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
        )

    def get_recipient_counts(self, obj):
        qs = obj.recipients.all()
        # Prefer annotated counts when present
        if hasattr(obj, "pending_count"):
            return {
                "total": obj.total_count,
                "pending": obj.pending_count,
                "sent": obj.sent_count,
                "failed": obj.failed_count,
                "skipped": obj.skipped_count,
            }
        return {
            "total": qs.count(),
            "pending": qs.filter(status=CampaignRecipient.Status.PENDING).count(),
            "sent": qs.filter(status=CampaignRecipient.Status.SENT).count(),
            "failed": qs.filter(status=CampaignRecipient.Status.FAILED).count(),
            "skipped": qs.filter(status=CampaignRecipient.Status.SKIPPED).count(),
        }


class MarketingCampaignCreateSerializer(serializers.Serializer):
    template_id = serializers.IntegerField()
    name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    filter_json = serializers.DictField(required=False)

    def validate_template_id(self, value):
        doctor: DoctorProfile = self.context["doctor"]
        if not MessageTemplate.objects.filter(
            id=value, doctor=doctor, is_active=True
        ).exists():
            raise serializers.ValidationError("Template not found.")
        return value
