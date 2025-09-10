# tests/test_webhook_retry.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S1.2")
@pytest.mark.django_db
def test_retry_same_orderreference_approved_is_idempotent(client):
    """
    Один и тот же APPROVED (одинаковый orderReference) приходит дважды.
    Ожидаем: подписка продлевается/создаётся ТОЛЬКО один раз, второй вебхук не меняет сроки.
    """
    user = TelegramUser.objects.create(user_id=777002222, username="retry", first_name="Retry")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    # Инвойс до оплаты
    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv = Invoice.objects.create(
        order_reference=ref,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,
        currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-ONCE",
    }

    # Первый APPROVED — должен активировать
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r1.status_code == 200

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    paid_at_1 = inv.paid_at

    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    first_expire = sub.expires_at

    # Второй такой же APPROVED (ретрай WayForPay)
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Проверяем идемпотентность: ничего не изменилось
    inv.refresh_from_db()
    sub.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.paid_at == paid_at_1
    assert sub.expires_at == first_expire
