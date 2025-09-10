# tests/test_amount_currency_fees.py
import json
import pytest
from tests.scenario_cov import covers

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus


@covers("S14.1")
@pytest.mark.django_db
def test_decimal_amount_currency_case_and_fee_are_handled(client):
    """
    Платёж с десятичной суммой (10.0), валютой в нижнем регистре ('uah') и комиссией (fee)
    должен пройти:
      - invoice -> APPROVED
      - сохраняется fee
      - создаётся/продлевается подписка
    """
    user = TelegramUser.objects.create(user_id=777004550, username="decfee", first_name="DecFee")
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
        "amount": 10.0,            # десятичное число → сравнение по int должно пройти
        "currency": "uah",         # нижний регистр → сравнение case-insensitive
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-DEC-OK",
        "fee": 0.35,               # комиссия передаётся и должна сохраниться
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    # fee сохранена (с учётом возможной конверсии в Decimal)
    assert inv.fee is not None
    assert float(inv.fee) == pytest.approx(0.35, rel=1e-6)

    # подписка создана и активна
    sub = Subscription.objects.get(user=user, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE
