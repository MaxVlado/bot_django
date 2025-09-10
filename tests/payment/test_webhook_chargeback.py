# tests/test_webhook_chargeback.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S6.4")
@pytest.mark.django_db
def test_chargeback_on_same_reference_does_not_downgrade_or_change_subscription(client):
    """
    Сначала APPROVED по orderReference -> инвойс оплачен, подписка активна.
    Затем приходит CHARGEBACK по тому же orderReference.
    Ожидаем:
      - статус инвойса остаётся APPROVED (не даунгрейдим)
      - подписка не меняется (срок и токены не трогаем)
    """
    user = TelegramUser.objects.create(user_id=777003111, username="chargeback", first_name="Chargeback")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    # 1) Создаём инвойс и подтверждаем оплатой
    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    payload_ok = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-OK",
        "recToken": "tok_keep",
        "cardPan": "444455******1111",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_ok), content_type="application/json")
    assert r1.status_code == 200

    inv = Invoice.objects.get(order_reference=ref)
    assert inv.payment_status == PaymentStatus.APPROVED
    paid_at_1 = inv.paid_at

    sub = Subscription.objects.get(user=user, bot_id=1)
    expires_1 = sub.expires_at
    token_1 = sub.card_token
    masked_1 = sub.card_masked

    # 2) Приходит CHARGEBACK по тому же orderReference
    payload_cb = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref,           # тот же ref
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "CHARGEBACK",
        "reasonCode": "cbk",
        "transactionId": "TX-CBK",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_cb), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Проверяем: инвойс остался APPROVED, подписка не изменилась
    inv.refresh_from_db()
    sub.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.paid_at == paid_at_1
    assert sub.expires_at == expires_1
    assert sub.card_token == token_1
    assert sub.card_masked == masked_1
