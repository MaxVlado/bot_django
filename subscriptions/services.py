# ================================================================
# subscriptions/services.py
# ================================================================
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Subscription, Plan, SubscriptionStatus
from core.models import TelegramUser
from payments.models import Invoice


class SubscriptionService:
    """Сервис для работы с подписками"""

    @staticmethod
    @transaction.atomic
    def create_subscription(user: TelegramUser, plan, *, duration_days: int | None = None) -> Subscription:
        """Создать подписку; duration_days можно переопределить снапшотом."""
        days = int(duration_days or plan.duration_days)
        starts_at = timezone.now()
        expires_at = starts_at + timedelta(days=days)
        sub = Subscription.objects.create(
            user=user,
            plan=plan,
            bot_id=plan.bot_id,
            status=SubscriptionStatus.TRIAL,
            starts_at=starts_at,
            expires_at=expires_at,
        )
        return sub

    @staticmethod
    @transaction.atomic
    def extend_subscription(subscription: Subscription, *, paid_at=None, invoice=None) -> Subscription:
        """
        Продлить подписку после оплаты, учитывая приоритет длительности:
        1) снапшот из invoice.raw_request_payload["planDurationDays"]
        2) если invoice есть — берем invoice.plan.duration_days
        3) иначе — subscription.plan.duration_days
        """
        now = timezone.now()

        # 1) определить длительность продления
        snap = None
        if invoice and isinstance(getattr(invoice, "raw_request_payload", None), dict):
            snap = invoice.raw_request_payload.get("planDurationDays")

        if snap is not None:
            try:
                days = int(snap)
            except (TypeError, ValueError):
                days = int(invoice.plan.duration_days) if invoice else int(subscription.plan.duration_days)
        elif invoice is not None:
            days = int(invoice.plan.duration_days)
        else:
            days = int(subscription.plan.duration_days)

        # 2) якорь продления
        anchor = subscription.expires_at if subscription.expires_at > now else now
        subscription.expires_at = anchor + timedelta(days=days)
        subscription.last_payment_date = paid_at or now
        subscription.status = SubscriptionStatus.ACTIVE

        # 3) рекуррентные данные карты (если прилетели в этом платеже)
        if invoice and invoice.rec_token:
            subscription.card_token = invoice.rec_token
            subscription.card_masked = invoice.card_pan

        subscription.save(update_fields=[
            "expires_at", "last_payment_date", "status", "card_token", "card_masked", "updated_at"
        ])
        return subscription

    @staticmethod
    @transaction.atomic
    def cancel_subscription(subscription: Subscription) -> bool:
        """Отменить подписку."""
        subscription.status = SubscriptionStatus.CANCELED
        subscription.save(update_fields=["status", "updated_at"])
        return True

    @staticmethod
    def get_expiring_subscriptions(bot_id: int, days_before: int = 3):
        """Подписки, истекающие в ближайшие N дней."""
        cutoff = timezone.now() + timedelta(days=days_before)
        return Subscription.objects.filter(
            bot_id=bot_id,
            status=SubscriptionStatus.ACTIVE,
            expires_at__lte=cutoff,
            expires_at__gt=timezone.now(),
        )
