# tests/test_webhook_amounts.py
import json
import pytest

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S15.1")
@pytest.mark.django_db
def test_approved_with_amount_mismatch_is_ignored(client):
    """
    Вебхук прислал APPROVED, но amount != amount в инвойсе.
    Ожидаем (безопасная политика):
      - инвойс НЕ становится APPROVED (остаётся PENDING)
      - подписка не создаётся/не продлевается
    """
    user = TelegramUser.objects.create(user_id=777002111, username="mismatch", first_name="Mismatch")
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

    # Вебхук говорит, что успешная оплата была на 9 (меньше ожидаемого)
    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": 9,                    # MISMATCH!
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-AMOUNT-MISMATCH",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    inv.refresh_from_db()
    # Безопасное ожидаемое поведение: не апрувим (оставляем PENDING) и не создаём подписку
    assert inv.payment_status == PaymentStatus.PENDING, "APPROVED с другой суммой не должен подтверждать инвойс"
    assert inv.paid_at is None
    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()
