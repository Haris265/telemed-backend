from django.contrib import admin

from .models import (
    ClinicSubscription,
    Invoice,
    LedgerEntry,
    Package,
    Payment,
    PurchaseRequest,
)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "clinic",
        "price",
        "duration_days",
        "max_doctors",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "clinic")
    search_fields = ("name", "code", "clinic__name")
    raw_id_fields = ("clinic",)
    prepopulated_fields = {"code": ("name",)}


@admin.register(ClinicSubscription)
class ClinicSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "clinic",
        "package",
        "status",
        "start_date",
        "end_date",
        "amount_paid",
        "is_active",
    )
    list_filter = ("status", "is_active")
    search_fields = ("clinic__name", "package__name")
    raw_id_fields = ("clinic", "package")


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ("clinic", "package", "status", "requested_by", "created_at")
    list_filter = ("status",)
    search_fields = ("clinic__name", "package__name")
    raw_id_fields = ("clinic", "package", "requested_by", "reviewed_by")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "clinic",
        "package",
        "amount",
        "status",
        "period_start",
        "period_end",
        "due_date",
        "paid_at",
    )
    list_filter = ("status",)
    search_fields = ("clinic__name", "package__name")
    raw_id_fields = (
        "clinic",
        "package",
        "subscription",
        "purchase_request",
        "created_by",
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("clinic", "amount", "method", "status", "paid_at", "recorded_by")
    list_filter = ("method", "status")
    search_fields = ("clinic__name",)
    raw_id_fields = (
        "clinic",
        "purchase_request",
        "subscription",
        "invoice",
        "recorded_by",
    )


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "clinic",
        "entry_type",
        "amount",
        "balance_after",
        "created_by",
        "created_at",
    )
    list_filter = ("entry_type",)
    search_fields = ("clinic__name",)
    raw_id_fields = ("clinic", "payment", "subscription", "created_by")
