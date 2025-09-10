# tests/test_webhook_non_success.py
import json
import pytest
from tests.scenario_cov import covers

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus


@covers("S3.1")
@pytest.mark.django_db
def test_only_declined_no_subscription_and_invoice_set_declined(client):
    """
    Приходит только DECLINED по инвойсу (Approved не было):
      - подписка не создаётся
      - статус инвойса становится DECLINED
    """
    user = TelegramUser.objects.create(user_id=777004333, username="decl", first_name="Decl")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv = Invoice.objects.create(
        order_reference=ref,
        user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "DECLINED",
        "reasonCode": "2001",
        "transactionId": "TX-ONLY-DECL",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.DECLINED
    assert not Subscription.objects.filter(user=user, bot_id=1).exists()


@covers("S3.2")
@pytest.mark.django_db
def test_only_expired_no_subscription_and_invoice_set_expired(client):
    """
    Приходит только EXPIRED по инвойсу (Approved не было):
      - подписка не создаётся
      - статус инвойса становится EXPIRED
    """
    user = TelegramUser.objects.create(user_id=777004334, username="expired", first_name="Expired")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv = Invoice.objects.create(
        order_reference=ref,
        user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref,
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
    assert not Subscription.objects.filter(user=user, bot_id=1).exists()


@covers("S3.3")
@pytest.mark.django_db
@pytest.mark.parametrize("trx_status", ["PENDING", "IN_PROCESS", "WAITING_AUTH_COMPLETE"])
def test_only_intermediate_statuses_do_not_create_subscription_and_keep_invoice_pending(client, trx_status):
    """
    Если WayForPay прислал только промежуточные статусы (без APPROVED),
    то:
      - подписка не создаётся
      - инвойс остаётся в состоянии ожидания (PENDING)
    """
    user = TelegramUser.objects.create(user_id=777004335, username="interm", first_name="Interm")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv = Invoice.objects.create(
        order_reference=ref,
        user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": trx_status,
        "reasonCode": "wait",
        "transactionId": f"TX-{trx_status}",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200  # наша вьюха отвечает 200 даже для промежуточных статусов

    inv.refresh_from_db()
    assert inv.payment_status in (PaymentStatus.PENDING, "PENDING")
    assert not Subscription.objects.filter(user=user, bot_id=1).exists()

