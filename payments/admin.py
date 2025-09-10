from django.contrib import admin
from .models import Invoice, VerifiedUser

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("order_reference", "user", "plan", "bot_id", "payment_status",
                    "amount", "currency", "paid_at", "created_at")
    list_filter = ("payment_status", "currency", "bot_id", "created_at")
    search_fields = ("order_reference", "user__username", "user__user_id")
    readonly_fields = ("raw_request_payload", "raw_response_payload")
    date_hierarchy = "created_at"

@admin.register(VerifiedUser)
class VerifiedUserAdmin(admin.ModelAdmin):
    list_display = ("user", "bot_id", "successful_payments_count",
                    "total_amount_paid", "last_payment_date", "first_payment_date")
    list_filter = ("bot_id",)
    search_fields = ("user__username", "user__user_id")
from django.contrib import admin

# Register your models here.
