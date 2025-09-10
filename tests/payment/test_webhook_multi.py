import json
import pytest
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers

@covers("S2.2", "S2.3", "S4.1", "S9.2")
@pytest.mark.django_db
def test_two_invoices_new_then_old_approved(client):
    """
    Сначала одобрили НОВЫЙ инвойс, потом пришёл APPROVED по СТАРОМУ.
    Ожидаем: подписка продлена дважды (≈ +2 * duration_days).
    """
    user = TelegramUser.objects.create(user_id=777000334, username="multi2", first_name="Multi2")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    # Сначала создаём СТАРЫЙ (он будет иметь меньший timestamp)
    order_ref_old = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv_old = Invoice.objects.create(
        order_reference=order_ref_old,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,
        currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    # Небольшая пауза -> создаём НОВЫЙ (у него timestamp больше)
    import time as _t
    _t.sleep(1.1)
    order_ref_new = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv_new = Invoice.objects.create(
        order_reference=order_ref_new,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,
        currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    # 1) Приходит APPROVED по НОВОМУ
    payload_new = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_new,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-NEW-First",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_new), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    first_expire = sub.expires_at
    now = timezone.now()
    from datetime import timedelta
    assert (now + timedelta(days=29, hours=23)) <= first_expire <= (now + timedelta(days=30, hours=1))

    # 2) Чуть позже приходит APPROVED по СТАРОМУ
    payload_old = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_old,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-OLD-Second",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_old), content_type="application/json")
    assert r2.status_code == 200

    sub.refresh_from_db()
    second_expire = sub.expires_at
    assert (first_expire + timedelta(days=29, hours=23)) <= second_expire <= (first_expire + timedelta(days=30, hours=1))
