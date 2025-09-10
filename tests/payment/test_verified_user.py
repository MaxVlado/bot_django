# tests/test_verified_user.py
import json
import pytest
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, SubscriptionStatus
from payments.models import Invoice, PaymentStatus, VerifiedUser
from tests.scenario_cov import covers


@covers("S13.2")
@pytest.mark.django_db
def test_verified_user_counters_increment_after_second_approved(client):
    """
    После двух успешных оплат:
      - successful_payments_count == 2
      - total_amount_paid == сумма двух платежей
      - last_payment_date обновился
    """
    user = TelegramUser.objects.create(user_id=777001999, username="vstat", first_name="VStat")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    # 1) Первый инвойс -> APPROVED
    ref1 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv1 = Invoice.objects.create(
        order_reference=ref1, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    payload1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref1,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-V-1",
        "cardPan": "444455******1111",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload1), content_type="application/json")
    assert r1.status_code == 200

    v1 = VerifiedUser.objects.get(user=user, bot_id=1)
    first_last_date = v1.last_payment_date
    assert v1.successful_payments_count == 1
    assert int(v1.total_amount_paid) == plan.price

    # 2) Второй инвойс -> APPROVED
    import time as _t
    ref2 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv2 = Invoice.objects.create(
        order_reference=ref2, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    payload2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref2,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-V-2",
        "cardPan": "555566******2222",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload2), content_type="application/json")
    assert r2.status_code == 200

    v1.refresh_from_db()
    assert v1.successful_payments_count == 2
    assert int(v1.total_amount_paid) == plan.price * 2
    assert v1.last_payment_date >= first_last_date
