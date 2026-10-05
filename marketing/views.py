from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsDoctor

from .models import (
    CampaignRecipient,
    MarketingCampaign,
    MarketingSubscription,
    MessageTemplate,
)
from .serializers import (
    CampaignRecipientSerializer,
    MarketingCampaignCreateSerializer,
    MarketingCampaignSerializer,
    MarketingSubscriptionSerializer,
    MessageTemplateSerializer,
)
from .services import (
    audience_preview,
    build_recipients,
    doctor_has_marketing,
    doctor_whatsapp_connected,
    process_campaign,
)


class AdminMarketingSubscriptionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]
    serializer_class = MarketingSubscriptionSerializer

    def get_queryset(self):
        qs = MarketingSubscription.objects.select_related("doctor", "doctor__user")
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
                qs = qs.filter(
                    is_active=True, start_date__lte=today, end_date__gte=today
                )
            else:
                qs = qs.exclude(
                    is_active=True, start_date__lte=today, end_date__gte=today
                )
        return qs.order_by("-created_at", "-id")


class AdminMarketingSubscriptionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdmin]
    serializer_class = MarketingSubscriptionSerializer
    queryset = MarketingSubscription.objects.select_related("doctor", "doctor__user")
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"


class DoctorMarketingStatusView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        doctor = request.user.doctor_profile
        return Response(
            {
                "marketing_enabled": doctor_has_marketing(doctor),
                "whatsapp_connected": doctor_whatsapp_connected(doctor),
            }
        )


class DoctorMessageTemplateListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsDoctor]
    serializer_class = MessageTemplateSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return MessageTemplate.objects.filter(doctor=self.request.user.doctor_profile)

    def perform_create(self, serializer):
        serializer.save(doctor=self.request.user.doctor_profile)


class DoctorMessageTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsDoctor]
    serializer_class = MessageTemplateSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return MessageTemplate.objects.filter(doctor=self.request.user.doctor_profile)

    def perform_destroy(self, instance):
        if instance.campaigns.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
        else:
            instance.delete()


class DoctorMarketingAudienceView(APIView):
    permission_classes = [IsDoctor]

    def get(self, request):
        doctor = request.user.doctor_profile
        filters = {
            "clinic_id": request.query_params.get("clinic_id"),
            "city": request.query_params.get("city"),
            "area": request.query_params.get("area"),
            "last_visit_days": request.query_params.get("last_visit_days"),
            "has_upcoming": request.query_params.get("has_upcoming"),
        }
        return Response(audience_preview(doctor, filters))


class DoctorMarketingCampaignListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsDoctor]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MarketingCampaignCreateSerializer
        return MarketingCampaignSerializer

    def get_queryset(self):
        return (
            MarketingCampaign.objects.filter(doctor=self.request.user.doctor_profile)
            .select_related("template")
            .annotate(
                total_count=Count("recipients"),
                pending_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.PENDING),
                ),
                sent_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.SENT),
                ),
                failed_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.FAILED),
                ),
                skipped_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.SKIPPED),
                ),
            )
        )

    def create(self, request, *args, **kwargs):
        doctor = request.user.doctor_profile
        serializer = MarketingCampaignCreateSerializer(
            data=request.data, context={"doctor": doctor}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        template = MessageTemplate.objects.get(
            id=data["template_id"], doctor=doctor, is_active=True
        )
        name = (data.get("name") or "").strip() or template.name
        campaign = MarketingCampaign.objects.create(
            doctor=doctor,
            template=template,
            name=name,
            filter_json=data.get("filter_json") or {},
            status=MarketingCampaign.Status.DRAFT,
        )
        build_recipients(campaign)
        out = MarketingCampaignSerializer(campaign, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class DoctorMarketingCampaignDetailView(generics.RetrieveAPIView):
    permission_classes = [IsDoctor]
    serializer_class = MarketingCampaignSerializer

    def get_queryset(self):
        return (
            MarketingCampaign.objects.filter(doctor=self.request.user.doctor_profile)
            .select_related("template")
            .annotate(
                total_count=Count("recipients"),
                pending_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.PENDING),
                ),
                sent_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.SENT),
                ),
                failed_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.FAILED),
                ),
                skipped_count=Count(
                    "recipients",
                    filter=Q(recipients__status=CampaignRecipient.Status.SKIPPED),
                ),
            )
        )


class DoctorMarketingCampaignRecipientsView(generics.ListAPIView):
    permission_classes = [IsDoctor]
    serializer_class = CampaignRecipientSerializer

    def get_queryset(self):
        campaign_id = self.kwargs["pk"]
        return CampaignRecipient.objects.filter(
            campaign_id=campaign_id,
            campaign__doctor=self.request.user.doctor_profile,
        ).select_related("patient")


class DoctorMarketingCampaignSendView(APIView):
    permission_classes = [IsDoctor]

    def post(self, request, pk):
        doctor = request.user.doctor_profile
        if not doctor_has_marketing(doctor):
            return Response(
                {"detail": "Marketing is not enabled. Contact admin to enable."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not doctor_whatsapp_connected(doctor):
            return Response(
                {"detail": "Connect WhatsApp before sending campaigns."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            campaign = MarketingCampaign.objects.select_related("template").get(
                pk=pk, doctor=doctor
            )
        except MarketingCampaign.DoesNotExist:
            return Response(
                {"detail": "Campaign not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if campaign.status == MarketingCampaign.Status.DONE:
            return Response(
                {"detail": "Campaign is already done."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if campaign.status == MarketingCampaign.Status.SENDING:
            # Allow continuing a partial batch.
            pass
        elif campaign.status not in (
            MarketingCampaign.Status.DRAFT,
            MarketingCampaign.Status.QUEUED,
            MarketingCampaign.Status.FAILED,
        ):
            return Response(
                {"detail": f"Cannot send campaign in status {campaign.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not campaign.recipients.exists():
            build_recipients(campaign)
        if not campaign.recipients.exists():
            return Response(
                {"detail": "No recipients matched the filters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        warning = ""
        if not (campaign.template.meta_template_name or "").strip():
            warning = (
                "Free-form text/image only delivers within Meta's 24-hour "
                "customer care window. Recipients outside that window may fail. "
                "Set a Meta-approved template name for marketing outside the window."
            )

        campaign.status = MarketingCampaign.Status.QUEUED
        campaign.save(update_fields=["status", "updated_at"])

        batch = int(request.data.get("batch_size") or 50)
        batch = max(1, min(batch, 200))
        counts = process_campaign(campaign.id, batch_size=batch)

        campaign.refresh_from_db()
        data = MarketingCampaignSerializer(campaign, context={"request": request}).data
        return Response(
            {
                "campaign": data,
                "batch": counts,
                "warning": warning,
            }
        )
