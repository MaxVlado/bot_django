# ================================================================
# subscriptions/models.py
# ================================================================
from datetime import timedelta

from django.db import models
from django.utils import timezone
from core.models import TelegramUser


class Plan(models.Model):
    """Тарифный план подписки"""
    bot_id = models.IntegerField(help_text="ID бота")
    name = models.CharField(max_length=255, help_text="Название плана")
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Цена")
    currency = models.CharField(max_length=3, default='UAH')
    duration_days = models.PositiveIntegerField(default=30, help_text="Длительность в днях")
    enabled = models.BooleanField(default=True)

    # Дополнительно
    description = models.TextField(blank=True)
    features = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscription_plans'
        unique_together = ('bot_id', 'name')
        indexes = [
            models.Index(fields=["bot_id", "enabled"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency}"


class SubscriptionStatus(models.TextChoices):
    TRIAL = 'trial', 'Trial'
    ACTIVE = 'active', 'Active'
    EXPIRED = 'expired', 'Expired'
    CANCELED = 'canceled', 'Canceled'


class Subscription(models.Model):
    """Подписка пользователя на план"""
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    bot_id = models.IntegerField(help_text="ID бота")

    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices,
                              default=SubscriptionStatus.ACTIVE)
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    last_payment_date = models.DateTimeField(null=True, blank=True)

    # Для рекуррентных платежей
    card_token = models.CharField(max_length=255, null=True, blank=True)
    card_masked = models.CharField(max_length=20, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        unique_together = ('user', 'plan', 'bot_id')
        indexes = [
            models.Index(fields=["bot_id", "user", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.plan} ({self.status})"

    def is_active(self) -> bool:
        """Активна ли подписка"""
        return self.status == SubscriptionStatus.ACTIVE and self.expires_at > timezone.now()

    def extend(self, days: int):
        """Продлить подписку"""
        now = timezone.now()
        if self.expires_at < now:
            self.expires_at = now
        self.expires_at += timedelta(days=days)
        self.status = SubscriptionStatus.ACTIVE
        self.last_payment_date = now
        self.save(update_fields=["expires_at", "status", "last_payment_date", "updated_at"])

    def cancel(self):
        """Отменить подписку"""
        self.status = SubscriptionStatus.CANCELED
        self.save(update_fields=["status", "updated_at"])
