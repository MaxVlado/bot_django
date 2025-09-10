from django.contrib import admin
from .models import PaymentNotification, ExpiryNotification


@admin.register(PaymentNotification)
class PaymentNotificationAdmin(admin.ModelAdmin):
    list_display = ("order_reference", "sent_at")
    search_fields = ("order_reference",)
    ordering = ("-sent_at",)


@admin.register(ExpiryNotification)
class ExpiryNotificationAdmin(admin.ModelAdmin):
    list_display = ("bot_id", "tg_user_id", "expires_on", "sent_at")
    list_filter = ("bot_id", "expires_on")
    search_fields = ("tg_user_id",)
    ordering = ("-sent_at",)
