from django.contrib import admin
from .models import Invoice, VerifiedUser
from django.utils import timezone
from django.contrib import admin, messages
from .models import Invoice, VerifiedUser, PaymentStatus
from payments.wayforpay.services import WayForPayService

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("order_reference", "user", "plan", "bot_id", "payment_status",
                    "amount", "currency", "paid_at", "created_at")
    list_filter = ("payment_status", "currency", "bot_id", "created_at","is_recurrent_manual")
    search_fields = ("order_reference", "user__username", "user__user_id")
    readonly_fields = ("raw_request_payload", "raw_response_payload")
    date_hierarchy = "created_at"

    fieldsets = (
        ('Основное', {
            'fields': ('order_reference', 'user', 'plan', 'bot_id', 'amount', 'currency')
        }),
        ('Статус', {
            'fields': ('payment_status', 'paid_at', 'is_recurrent_manual')
        }),
        ('Данные транзакции', {
            'fields': ('transaction_id', 'auth_code', 'card_pan', 'card_type', 
                      'issuer_bank', 'issuer_country', 'payment_system', 'rec_token')
        }),
        ('Дополнительно', {
            'fields': ('phone', 'email', 'fee', 'rrn', 'approval_code', 'terminal', 'reason_code'),
            'classes': ('collapse',)
        }),
        ('Отладка', {
            'fields': ('raw_request_payload', 'raw_response_payload'),
            'classes': ('collapse',)
        }),
    )

    actions = ['approve_and_activate']

@admin.register(VerifiedUser)
class VerifiedUserAdmin(admin.ModelAdmin):
    list_display = ("user", "bot_id", "successful_payments_count",
                    "total_amount_paid", "last_payment_date", "first_payment_date")
    list_filter = ("bot_id",)
    search_fields = ("user__username", "user__user_id")
from django.contrib import admin


@admin.action(description="💰 Погасить и активировать подписку")
def approve_and_activate(self, request, queryset):
    """Ручное погашение invoice и активация подписки"""
    count = 0
    for invoice in queryset:
        if invoice.payment_status == PaymentStatus.APPROVED:
            continue
        
        # Помечаем как оплаченный
        invoice.payment_status = PaymentStatus.APPROVED
        invoice.paid_at = timezone.now()
        invoice.save()
        
        # Обрабатываем платеж
        service = WayForPayService(bot_id=invoice.bot_id)
        service.process_manual_payment(invoice)
    count += 1

    self.message_user(request, f"Активировано подписок: {count}", messages.SUCCESS) 
