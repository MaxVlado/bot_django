# tests/test_webhook_basic.py
import json
from datetime import timedelta
import time

import pytest
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers

@covers("S1.1")
@pytest.mark.django_db
def test_webhook_approved_creates_subscription(client):
    # Подготовка: пользователь, план, инвойс (PENDING)
    user = TelegramUser.objects.create(user_id=777000111, username="autotest", first_name="Auto")
    plan = Plan.objects.create(bot_id=1, name="Test Plan", price=10, currency="UAH", duration_days=30, enabled=True)
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

    # Действие: шлём вебхук APPROVED
    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "authCode": "A1B2C3",
        "cardPan": "444455******1111",
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-TEST-1",
        "recToken": "tok_test_abc",
        "paymentSystem": "VISA",
        "issuerBankName": "Test Bank",
        "issuerBankCountry": "UA",
    }
    resp = client.post(
        "/api/payments/wayforpay/webhook/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "accept"

    # Проверки: инвойс
    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.paid_at is not None
    assert inv.rec_token == "tok_test_abc"

    # Проверки: подписка создана и активна с правильным сроком
    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE
    # expires_at ≈ now + plan.duration_days (с небольшим допуском)
    now = timezone.now()
    expected_min = now + timedelta(days=plan.duration_days) - timedelta(minutes=1)
    expected_max = now + timedelta(days=plan.duration_days) + timedelta(minutes=1)
    assert expected_min <= sub.expires_at <= expected_max

@covers("S1.2","S9.1")
@pytest.mark.django_db
def test_webhook_approved_is_idempotent(client):
    # Подготовка
    user = TelegramUser.objects.create(user_id=777000222, username="dup", first_name="Dup")
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
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-DUP-1",
        "recToken": "tok_dup",
    }

    # 1-й вебхук -> создаст/продлит подписку
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r1.status_code == 200
    inv.refresh_from_db()
    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    expires_first = sub.expires_at
    updated_first = inv.updated_at

    # 2-й вебхук (повтор того же orderReference) -> ничего не меняет
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r2.status_code == 200

    inv.refresh_from_db()
    sub.refresh_from_db()
    assert sub.expires_at == expires_first, "повторный APPROVED не должен продлевать ещё раз"
    assert inv.updated_at == updated_first, "идемпотентность: повтор не должен мутировать инвойс"

@covers("S2.1")
@pytest.mark.django_db
def test_two_invoices_old_then_new_approved(client):
    """
    Сценарий: пользователь несколько раз нажал «Оплатить».
    Пришли два APPROVED по разным orderReference: сначала по старому, затем по новому.
    Ожидаем: подписка продлилась дважды (≈ +2 * duration_days).
    """
    user = TelegramUser.objects.create(user_id=777000333, username="multi", first_name="Multi")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    # старый инвойс
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

    # небольшой разрыв по времени чтобы гарантировать "новизну" второго инвойса
    time.sleep(1.1)

    # новый инвойс
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

    # 1) APPROVED по старому
    payload_old = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_old,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-OLD",
        "recToken": "tok_old",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_old), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    first_expire = sub.expires_at
    # после первого продления: ≈ now + 30д
    now = timezone.now()
    assert (now + timedelta(days=29, hours=23)) <= first_expire <= (now + timedelta(days=30, hours=1))

    # 2) APPROVED по новому
    payload_new = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_new,
        "amount": float(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-NEW",
        "recToken": "tok_new",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_new), content_type="application/json")
    assert r2.status_code == 200

    sub.refresh_from_db()
    second_expire = sub.expires_at

    # второе продление добавляет ещё 30д к max(expires_at, now) → примерно +30д к first_expire
    assert (first_expire + timedelta(days=29, hours=23)) <= second_expire <= (first_expire + timedelta(days=30, hours=1))