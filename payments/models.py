# ================================================================
# payments/models.py
# ================================================================
from django.db import models
from django.utils import timezone
from core.models import TelegramUser, Bot
from subscriptions.models import Plan, Subscription


class PaymentStatus(models.TextChoices):
    NEW = 'NEW', 'New'
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    DECLINED = 'DECLINED', 'Declined'
    REFUNDED = 'REFUNDED', 'Refunded'
    EXPIRED = 'EXPIRED', 'Expired'


class Invoice(models.Model):
    """Счет на оплату"""
    order_reference = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    bot_id = models.IntegerField()

    # Сумма и валюта
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='UAH')

    # Статус платежа
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NEW
    )

    # Данные транзакции от WayForPay
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    auth_code = models.CharField(max_length=50, null=True, blank=True)
    card_pan = models.CharField(max_length=20, null=True, blank=True)
    card_type = models.CharField(max_length=50, null=True, blank=True)
    issuer_bank = models.CharField(max_length=100, null=True, blank=True)
    issuer_country = models.CharField(max_length=3, null=True, blank=True)
    payment_system = models.CharField(max_length=50, null=True, blank=True)
    reason_code = models.CharField(max_length=191, null=True, blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    rrn = models.CharField(max_length=50, null=True, blank=True)
    approval_code = models.CharField(max_length=50, null=True, blank=True)
    terminal = models.CharField(max_length=50, null=True, blank=True)
    rec_token = models.CharField(max_length=255, null=True, blank=True)

    # Контактные данные
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)

    # Raw данные для отладки
    raw_request_payload = models.JSONField(null=True, blank=True)
    raw_response_payload = models.JSONField(null=True, blank=True)

    # Временные метки
    notified_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    is_recurrent_manual = models.BooleanField(
        default=False, 
        verbose_name="Рекуррентная (бессрочная)",
        help_text="Для ручной активации: подписка до 9999-12-31"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_invoices'

    def __str__(self):
        return f"Invoice {self.order_reference} - {self.amount} {self.currency}"

    @classmethod
    def generate_order_reference(cls, bot_id: int, user_id: int, plan_id: int) -> str:
        """
        Генерация orderReference в формате: ORDER_timestamp+random3_user_plan
        
        Пример: ORDER_1758606042kjI_407673079_2
        
        Структура:
        - PREFIX: ORDER_
        - timestamp (секунды): 1758606042
        - random 3 символа: kjI
        - user_id (telegram): 407673079
        - plan_id: 2
        """
        import time
        import random
        import string
        
        # Timestamp в секундах (как в PHP)
        timestamp = int(time.time())
        
        # 3 случайных символа (буквы и цифры, как Str::random(3) в PHP)
        random_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=3))
        
        # Формат: ORDER_timestamp+random_user_plan
        order_reference = f"ORDER_{timestamp}{random_chars}_{user_id}_{plan_id}"
        
        return order_reference

    def is_approved(self) -> bool:
        return self.payment_status == PaymentStatus.APPROVED

    def is_refunded(self) -> bool:
        return self.payment_status == PaymentStatus.REFUNDED

    def mark_as_paid(self):
        """Отметить счет как оплаченный"""
        self.payment_status = PaymentStatus.APPROVED
        self.paid_at = timezone.now()
        self.save()


class VerifiedUser(models.Model):
    """Пользователь, верифицированный через платежи"""
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    bot_id = models.IntegerField()

    # Данные с первого успешного платежа
    first_payment_date = models.DateTimeField()
    card_masked = models.CharField(max_length=20, null=True, blank=True)
    payment_system = models.CharField(max_length=50, null=True, blank=True)
    issuer_bank = models.CharField(max_length=100, null=True, blank=True)

    # Статистика для антифрода
    successful_payments_count = models.IntegerField(default=1)
    total_amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    last_payment_date = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'verified_users'
        unique_together = ('user', 'bot_id')

    def __str__(self):
        return f"Verified: {self.user} for bot {self.bot_id}"

    def update_payment_stats(self, invoice: Invoice):
        """Обновить статистику платежей"""
        self.successful_payments_count += 1
        self.total_amount_paid += invoice.amount
        self.last_payment_date = timezone.now()
        if invoice.card_pan:
            self.card_masked = invoice.card_pan
        if invoice.payment_system:
            self.payment_system = invoice.payment_system
        if invoice.issuer_bank:
            self.issuer_bank = invoice.issuer_bank
        self.save()

    @classmethod
    def verify_user_from_payment(cls, invoice: Invoice):
        """Верифицировать пользователя на основе платежа"""
        verified_user, created = cls.objects.get_or_create(
            user=invoice.user,
            bot_id=invoice.bot_id,
            defaults={
                'first_payment_date': timezone.now(),
                'card_masked': invoice.card_pan,
                'payment_system': invoice.payment_system,
                'issuer_bank': invoice.issuer_bank,
                'total_amount_paid': invoice.amount,
                'last_payment_date': timezone.now(),
            }
        )

        if not created:
            verified_user.update_payment_stats(invoice)

        return verified_user


class MerchantConfig(models.Model):
    """WayForPay-конфигурация для конкретного бота"""
    bot = models.OneToOneField(Bot, on_delete=models.CASCADE, related_name="merchant_config")
    merchant_account = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)
    pay_url = models.URLField(default="https://secure.wayforpay.com/pay")
    api_url = models.URLField(default="https://api.wayforpay.com/api")
    django_api_base = models.URLField(
        default="https://dev.profilinggroup.com/api/payments/wayforpay",
        help_text="URL Django API для создания инвойсов (НЕ WayForPay API!)"
    )
    verify_signature = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_configs"

    def __str__(self):
        return f"MerchantConfig for Bot#{self.bot.bot_id}"
