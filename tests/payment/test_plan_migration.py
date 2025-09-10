import json
import pytest
from datetime import timedelta
from django.utils import timezone

from tests.scenario_cov import covers
from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus


@covers("S18.2")
@pytest.mark.django_db
def test_plan_duration_changed_after_invoice_extend_uses_snapshot_from_invoice(client):
    """
    Инвойс создан, когда у плана duration_days=30.
    До вебхука админ меняет план на 45 дней.
    Ожидаем: продление идёт на 30 (снапшот), а НЕ на 45.
    """
    user = TelegramUser.objects.create(user_id=777004770, username="migrate", first_name="Migrate")
    plan = Plan.objects.create(bot_id=1, name="Plan-Old30", price=10, currency="UAH", duration_days=30, enabled=True)

    # Первый успех создаёт подписку (30 дней)
    ref1 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref1, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
        # снапшот длительности фиксируем в raw_request_payload (минимальный путь без миграций схемы)
        raw_request_payload={"planDurationDays": 30},
    )
    p1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref1,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-MIG-1",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p1), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE
    first_expire = sub.expires_at

    # Админ меняет длительность плана на 45 (миграция структуры)
    plan.duration_days = 45
    plan.name = "Plan-New45"
    plan.save(update_fields=["duration_days", "name", "updated_at"])

    # Второй инвойс: был создан, когда ещё считали 30 (фиксируем снапшот в инвойсе)
    ref2 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref2, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
        raw_request_payload={"planDurationDays": 30},
    )
    p2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref2,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-MIG-2",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p2), content_type="application/json")
    assert r2.status_code == 200

    # Проверяем: прибавилось именно ~30 дней, а не 45
    sub.refresh_from_db()
    assert (first_expire + timedelta(days=29, hours=23)) <= sub.expires_at <= (first_expire + timedelta(days=30, hours=1))
