from django.contrib import admin

from .models import (
    CampaignRecipient,
    MarketingCampaign,
    MarketingSubscription,
    MessageTemplate,
)


@admin.register(MarketingSubscription)
class MarketingSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "doctor",
        "amount",
        "start_date",
        "end_date",
        "is_active",
        "payment_method",
        "created_at",
    )
    list_filter = ("is_active", "payment_method")
    search_fields = (
        "doctor__first_name",
        "doctor__last_name",
        "doctor__user__email",
    )
    raw_id_fields = ("doctor",)


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "doctor", "meta_template_name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "body", "meta_template_name", "doctor__first_name")
    raw_id_fields = ("doctor",)


class CampaignRecipientInline(admin.TabularInline):
    model = CampaignRecipient
    extra = 0
    readonly_fields = ("patient", "phone", "status", "error", "sent_at")
    can_delete = False


@admin.register(MarketingCampaign)
class MarketingCampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "doctor", "template", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "doctor__first_name", "doctor__last_name")
    raw_id_fields = ("doctor", "template")
    inlines = [CampaignRecipientInline]


@admin.register(CampaignRecipient)
class CampaignRecipientAdmin(admin.ModelAdmin):
    list_display = ("campaign", "phone", "status", "sent_at")
    list_filter = ("status",)
    search_fields = ("phone",)
    raw_id_fields = ("campaign", "patient")
