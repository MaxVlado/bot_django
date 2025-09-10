# tests/test_invoice_management.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone

from tests.scenario_cov import covers
from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus


@covers("S2.4")
@pytest.mark.django_db
def test_pay_different_plan_same_bot_extends_existing_subscription_without_switching_plan(client):
    """
    Есть активная подписка по плану A (30 дней).
    Пользователь оплачивает другой план B (60 дней) того же бота.

    Ожидаем:
      - инвойс по B → APPROVED
      - подписка остаётся одна (по боту), не создаётся вторая
      - subscription.plan НЕ меняется (остаётся A)
      - expires_at продлевается на duration_days плана из инвойса (B = 60)
    """
    user = TelegramUser.objects.create(user_id=777004440, username="diff_plan", first_name="Diff")
    plan_a = Plan.objects.create(bot_id=1, name="Plan-A30", price=10, currency="UAH", duration_days=30, enabled=True)
    plan_b = Plan.objects.create(bot_id=1, name="Plan-B60", price=20, currency="UAH", duration_days=60, enabled=True)

    # 1) Первая оплата -> создаёт подписку по A
    ref_a = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan_a.id)
    Invoice.objects.create(
        order_reference=ref_a, user=user, plan=plan_a, bot_id=1,
        amount=plan_a.price, currency=plan_a.currency, payment_status=PaymentStatus.PENDING,
    )
    p1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref_a,
        "amount": int(plan_a.price),
        "currency": plan_a.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-A",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p1), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, bot_id=1)
    assert sub.plan_id == plan_a.id and sub.status == SubscriptionStatus.ACTIVE
    first_expire = sub.expires_at

    # 2) Оплата по ДРУГОМУ плану B того же бота
    ref_b = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan_b.id)
    inv_b = Invoice.objects.create(
        order_reference=ref_b, user=user, plan=plan_b, bot_id=1,
        amount=plan_b.price, currency=plan_b.currency, payment_status=PaymentStatus.PENDING,
    )
    p2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref_b,
        "amount": int(plan_b.price),
        "currency": plan_b.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-B",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p2), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Проверки
    inv_b.refresh_from_db()
    assert inv_b.payment_status == PaymentStatus.APPROVED

    # остаётся ровно 1 подписка по боту
    subs = Subscription.objects.filter(user=user, bot_id=1)
    assert subs.count() == 1
    sub = subs.first()

    # план подписки НЕ переключили — остался A
    assert sub.plan_id == plan_a.id

    # срок продлился на длительность плана ИНВОЙСА (B = 60 дней)
    sub.refresh_from_db()
    assert (first_expire + timedelta(days=59, hours=23)) <= sub.expires_at <= (first_expire + timedelta(days=60, hours=1))
