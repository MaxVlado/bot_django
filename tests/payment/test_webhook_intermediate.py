# tests/test_webhook_intermediate.py
import json
import pytest

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S3.4")
@pytest.mark.django_db
def test_waiting_auth_complete_does_not_change_subscription(client):
    """
    Промежуточный статус 3DS: WAITING_AUTH_COMPLETE.
    Ожидаем: подписка не создаётся/не продлевается, инвойс остаётся PENDING.
    """
    user = TelegramUser.objects.create(user_id=777000444, username="3ds", first_name="StepUp")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=5, currency="UAH", duration_days=30, enabled=True)
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
        "transactionStatus": "WAITING_AUTH_COMPLETE",
        "reasonCode": "3DS",
        "transactionId": "TX-3DS-1",
    }

    resp = client.post(
        "/api/payments/wayforpay/webhook/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.PENDING
    assert inv.paid_at is None

    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()
