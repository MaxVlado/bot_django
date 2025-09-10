# tests/test_webhook_formats.py
import json
import pytest
from tests.scenario_cov import covers

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus


@covers("S8.2")
@pytest.mark.django_db
def test_unparsable_order_reference_is_handled_by_exact_lookup(client):
    """
    orderReference имеет «странный» формат (не наш bot_user_plan_ts...).
    Мы всё равно должны корректно обработать вебхук:
      - найти инвойс по точному значению orderReference
      - подтвердить оплату
      - создать/продлить подписку
    """
    user = TelegramUser.objects.create(user_id=777002888, username="weirdref", first_name="Weird")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    # Преднамеренно «кривой» ref (с тире/символами)
    weird_ref = "WFP#INV-αβγ-001"

    inv = Invoice.objects.create(
        order_reference=weird_ref,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,
        currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": weird_ref,          # тот же «непарсибельный» ref
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-WEIRD-OK",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.paid_at is not None

    sub = Subscription.objects.get(user=user, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE
