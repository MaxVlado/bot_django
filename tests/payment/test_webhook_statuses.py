# tests/test_webhook_statuses.py
import json
import pytest

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S3.1")
@pytest.mark.django_db
def test_only_declined_does_not_create_or_extend_subscription(client):
    """
    Приходит единственный вебхук со статусом DECLINED.
    Ожидаем:
      - инвойс получает статус DECLINED
      - подписка не создаётся и не продлевается
    """
    user = TelegramUser.objects.create(user_id=777001888, username="decl_only", first_name="DeclOnly")
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

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "DECLINED",
        "reasonCode": "not_enough_funds",
        "transactionId": "TX-ONLY-DECL",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.DECLINED
    assert inv.paid_at is None

    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()


@covers("S3.2")
@pytest.mark.django_db
def test_only_expired_does_not_create_or_extend_subscription(client):
    """
    Приходит единственный вебхук со статусом EXPIRED (счёт протух).
    Ожидаем:
      - инвойс получает статус EXPIRED
      - подписка не создаётся и не продлевается
    """
    user = TelegramUser.objects.create(user_id=777001889, username="expired_only", first_name="ExpiredOnly")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)
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

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "EXPIRED",
        "reasonCode": "timeout",
        "transactionId": "TX-ONLY-EXP",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.EXPIRED
    assert inv.paid_at is None

    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()
