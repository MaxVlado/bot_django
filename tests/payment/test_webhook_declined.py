# tests/test_webhook_declined.py
import json
import pytest

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S3.5")
@pytest.mark.django_db
def test_declined_with_amount_mismatch_does_not_change_subscription(client):
    """
    Частичный DECLINED: сумма в вебхуке меньше суммы инвойса.
    Ожидаем: статус инвойса -> DECLINED, подписка не создаётся/не продлевается.
    """
    user = TelegramUser.objects.create(user_id=777000555, username="decl", first_name="Decl")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=10, currency="UAH", duration_days=30, enabled=True)
    order_ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)

    inv = Invoice.objects.create(
        order_reference=order_ref,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,      # ожидаемая сумма = 10
        currency=plan.currency, # UAH
        payment_status=PaymentStatus.PENDING,
    )

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": 9,  # меньше, чем в инвойсе
        "currency": plan.currency,
        "transactionStatus": "DECLINED",
        "reasonCode": "insufficient_funds_partial",
        "transactionId": "TX-DECL-PART",
    }

    resp = client.post(
        "/api/payments/wayforpay/webhook/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.DECLINED
    assert inv.paid_at is None

    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()
