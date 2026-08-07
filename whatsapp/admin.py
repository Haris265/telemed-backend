from django.contrib import admin

from .models import WhatsAppSession


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = ("phone", "state", "updated_at")
    list_filter = ("state",)
    search_fields = ("phone",)
