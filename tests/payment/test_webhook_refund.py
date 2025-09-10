# tests/test_webhook_refund.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S6.1")
@pytest.mark.django_db
def test_full_refunded_after_approved_does_not_downgrade(client):
    """
    Сначала успешная оплата (APPROVED) -> активируется/продлевается подписка.
    Затем приходит REFUNDED по тому же orderReference.
    Ожидаем: статус инвойса остаётся APPROVED, подписка остаётся ACTIVE без изменений.
    """
    user = TelegramUser.objects.create(user_id=777001000, username="refund", first_name="Refund")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    order_ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv = Invoice.objects.create(
        order_reference=order_ref,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,
        currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    # 1) APPROVED
    payload_ok = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": float(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-OK",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_ok), content_type="application/json")
    assert r1.status_code == 200

    inv.refresh_from_db()
    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    first_expire = sub.expires_at
    assert inv.payment_status == PaymentStatus.APPROVED
    assert sub.status == SubscriptionStatus.ACTIVE

    # 2) REFUNDED по тому же orderReference
    payload_ref = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": float(plan.price),
        "currency": plan.currency,
        "transactionStatus": "REFUNDED",  # даунгрейд после APPROVED -> должен быть проигнорирован
        "reasonCode": "refund_full",
        "transactionId": "TX-REFUND",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_ref), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Проверяем: инвойс и подписка НЕ изменились
    inv.refresh_from_db()
    sub.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED, "даунгрейд статуса инвойса недопустим"
    assert sub.status == SubscriptionStatus.ACTIVE, "подписка не должна отключаться из-за REFUNDED"
    assert sub.expires_at == first_expire, "REFUNDED не должен менять срок подписки"


@covers("S6.2")
@pytest.mark.django_db
def test_partial_refunded_after_approved_does_not_change_subscription(client):
    """
    Частичный возврат после успешной оплаты:
    - подписка остаётся ACTIVE
    - срок не меняется
    - инвойс не «даунгрейдится» (остаётся APPROVED)
    """
    user = TelegramUser.objects.create(user_id=777001555, username="refund_part", first_name="RefundPart")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    order_ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv = Invoice.objects.create(
        order_reference=order_ref,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,      # 10
        currency=plan.currency, # UAH
        payment_status=PaymentStatus.PENDING,
    )

    # 1) Успешная оплата
    ok = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-OK-PART",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(ok), content_type="application/json")
    assert r1.status_code == 200

    inv.refresh_from_db()
    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    first_expire = sub.expires_at
    assert inv.payment_status == PaymentStatus.APPROVED
    assert sub.status == SubscriptionStatus.ACTIVE

    # 2) Частичный REFUNDED (вернули часть суммы) — политика: не трогаем подписку/инвойс
    partial_refund = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(plan.price) - 3,     # вернули 3 из 10, условно
        "currency": plan.currency,
        "transactionStatus": "REFUNDED",
        "reasonCode": "refund_partial",
        "transactionId": "TX-REFUND-PART",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(partial_refund), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    inv.refresh_from_db()
    sub.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED, "частичный возврат не должен понижать статус оплаты"
    assert sub.status == SubscriptionStatus.ACTIVE, "подписка остаётся активной при частичном возврате"
    assert sub.expires_at == first_expire, "срок подписки не должен меняться"