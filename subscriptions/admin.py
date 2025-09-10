from django.contrib import admin
from .models import Plan, Subscription

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("id", "bot_id", "name", "price", "currency", "duration_days", "enabled", "created_at")
    list_filter = ("bot_id", "enabled", "currency")
    search_fields = ("name",)

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "plan", "bot_id", "status", "starts_at", "expires_at", "last_payment_date")
    list_filter = ("bot_id", "status")
    search_fields = ("user__username", "user__user_id")
