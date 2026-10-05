from django.urls import path

from .views import (
    AdminMarketingSubscriptionDetailView,
    AdminMarketingSubscriptionListCreateView,
    DoctorMarketingAudienceView,
    DoctorMarketingCampaignDetailView,
    DoctorMarketingCampaignListCreateView,
    DoctorMarketingCampaignRecipientsView,
    DoctorMarketingCampaignSendView,
    DoctorMarketingStatusView,
    DoctorMessageTemplateDetailView,
    DoctorMessageTemplateListCreateView,
)

admin_marketing_urlpatterns = [
    path(
        "marketing/subscriptions/",
        AdminMarketingSubscriptionListCreateView.as_view(),
        name="admin-marketing-subscriptions",
    ),
    path(
        "marketing/subscriptions/<uuid:uuid>/",
        AdminMarketingSubscriptionDetailView.as_view(),
        name="admin-marketing-subscription-detail",
    ),
]

doctor_marketing_urlpatterns = [
    path(
        "marketing/status/",
        DoctorMarketingStatusView.as_view(),
        name="doctor-marketing-status",
    ),
    path(
        "marketing/templates/",
        DoctorMessageTemplateListCreateView.as_view(),
        name="doctor-marketing-templates",
    ),
    path(
        "marketing/templates/<int:pk>/",
        DoctorMessageTemplateDetailView.as_view(),
        name="doctor-marketing-template-detail",
    ),
    path(
        "marketing/audience/",
        DoctorMarketingAudienceView.as_view(),
        name="doctor-marketing-audience",
    ),
    path(
        "marketing/campaigns/",
        DoctorMarketingCampaignListCreateView.as_view(),
        name="doctor-marketing-campaigns",
    ),
    path(
        "marketing/campaigns/<int:pk>/",
        DoctorMarketingCampaignDetailView.as_view(),
        name="doctor-marketing-campaign-detail",
    ),
    path(
        "marketing/campaigns/<int:pk>/recipients/",
        DoctorMarketingCampaignRecipientsView.as_view(),
        name="doctor-marketing-campaign-recipients",
    ),
    path(
        "marketing/campaigns/<int:pk>/send/",
        DoctorMarketingCampaignSendView.as_view(),
        name="doctor-marketing-campaign-send",
    ),
]
