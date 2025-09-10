# tests/test_webhook_admin.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S11.1")
@pytest.mark.django_db
def test_admin_stop_now_then_next_approved_extends_from_now(client):
    """
    Админ принудительно «остановил» подписку (EXPIRED прямо сейчас).
    Приходит следующий APPROVED -> подписка должна продлиться от текущего времени и стать ACTIVE.
    """
    user = TelegramUser.objects.create(user_id=777001111, username="admstop", first_name="AdminStop")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    # Существующая подписка, принудительно истекшая (как после "Стоп сейчас")
    sub = Subscription.objects.create(
        user=user,
        plan=plan,
        bot_id=1,
        status=SubscriptionStatus.EXPIRED,
        starts_at=timezone.now() - timedelta(days=40),
        expires_at=timezone.now() - timedelta(minutes=1),  # уже в прошлом
    )

    # Новый инвойс (ожидаем, что APPROVED продлит от now, а не от старого expires_at)
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
        "transactionId": "TX-ADMIN-RESUME",
        "recToken": "tok_after_stop",
        "cardPan": "444455******1111",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    # Проверки: подписка стала ACTIVE и продлена от текущего времени
    sub.refresh_from_db()
    now = timezone.now()
    expected_min = now + timedelta(days=plan.duration_days) - timedelta(minutes=1)
    expected_max = now + timedelta(days=plan.duration_days) + timedelta(minutes=1)

    assert sub.status == SubscriptionStatus.ACTIVE, "подписка должна снова стать активной"
    assert expected_min <= sub.expires_at <= expected_max, "продление должно считаться от now (а не от старого прошлого expires_at)"


@covers("S11.2")
@pytest.mark.django_db
def test_invoice_uses_its_amount_currency_even_if_plan_changed(client):
    """
    Инвойс выписан при цене=10, валюте=UAH, план потом изменён:
      - price=99, currency=USD, enabled=False.
    Приходит APPROVED по инвойсу -> подписка должна продлиться,
    а инвойс остаться с исходными суммой/валютой.
    """
    user = TelegramUser.objects.create(user_id=777001444, username="planchg", first_name="PlanChg")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH",
                               duration_days=30, enabled=True)

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

    # Изменяем план ПОСЛЕ выпуска инвойса (другая цена/валюта, план отключен)
    plan.price = 99
    plan.currency = "USD"
    plan.enabled = False
    plan.save()

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(inv.amount),     # 10 (из инвойса)
        "currency": inv.currency,        # "UAH"
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-PLAN-CHANGED",
    }

    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    # Инвойс подтверждён и не «переписан» текущими полями плана
    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.amount == 10
    assert inv.currency == "UAH"

    # Подписка активна и продлена на duration_days
    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE
    now = timezone.now()
    expected_min = now + timedelta(days=plan.duration_days) - timedelta(minutes=1)
    expected_max = now + timedelta(days=plan.duration_days) + timedelta(minutes=1)
    assert expected_min <= sub.expires_at <= expected_max


@covers("S11.3")
@pytest.mark.django_db
def test_admin_changed_invoice_plan_id_extend_uses_invoice_plan_without_new_subscription(client):
    """
    Есть активная подписка (создана оплатой по плану A, 30 дней).
    Админ вручную меняет у НОВОГО инвойса plan_id -> план B (60 дней) и сумму/валюту под него.
    Приходит APPROVED по этому инвойсу:
      - продлеваем СУЩЕСТВУЮЩУЮ подписку ещё на 60 дней (по invoice.plan.duration_days)
      - subscription.plan НЕ меняем (остаётся план A)
      - второй подписки у того же бота не появляется
    """
    user = TelegramUser.objects.create(user_id=777002555, username="admin_fix", first_name="AdminFix")

    plan_a = Plan.objects.create(bot_id=1, name="Plan-A30", price=10, currency="UAH", duration_days=30, enabled=True)
    plan_b = Plan.objects.create(bot_id=1, name="Plan-B60", price=20, currency="UAH", duration_days=60, enabled=True)

    # 1) Первая оплата по плану A -> создаёт подписку
    ref1 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan_a.id)
    Invoice.objects.create(
        order_reference=ref1, user=user, plan=plan_a, bot_id=1,
        amount=plan_a.price, currency=plan_a.currency, payment_status=PaymentStatus.PENDING,
    )
    p1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref1,
        "amount": int(plan_a.price),
        "currency": plan_a.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-A-FIRST",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p1), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, bot_id=1)
    assert sub.plan_id == plan_a.id and sub.status == SubscriptionStatus.ACTIVE
    first_expire = sub.expires_at

    # 2) Создаём второй инвойс (первоначально под план A), затем АДМИН меняет его на план B
    ref2 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan_a.id)
    inv2 = Invoice.objects.create(
        order_reference=ref2, user=user, plan=plan_a, bot_id=1,
        amount=plan_a.price, currency=plan_a.currency, payment_status=PaymentStatus.PENDING,
    )
    # админ правит инвойс
    inv2.plan = plan_b
    inv2.amount = plan_b.price           # чтобы прошла наша валидация суммы
    inv2.currency = plan_b.currency
    inv2.save(update_fields=["plan", "amount", "currency", "updated_at"])

    # 3) Приходит APPROVED по инвойсу с планом B
    p2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref2,
        "amount": int(inv2.amount),
        "currency": inv2.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-B-ADMIN-CHANGED",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p2), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Проверки
    inv2.refresh_from_db()
    assert inv2.payment_status == PaymentStatus.APPROVED
    assert inv2.subscription_id is not None

    sub.refresh_from_db()
    from datetime import timedelta
    # продление ровно на 60 дней (допускаем ±1 час окна)
    assert (first_expire + timedelta(days=59, hours=23)) <= sub.expires_at <= (first_expire + timedelta(days=60, hours=1))
    # план подписки не меняем
    assert sub.plan_id == plan_a.id

    # второй подписки у того же бота не появилось
    assert Subscription.objects.filter(user=user, bot_id=1).count() == 1



@covers("S11.4")
@pytest.mark.django_db
def test_admin_manual_adjust_anchor_max_of_expires_at_or_now(client):
    """
    Админ вручную меняет expires_at у подписки.
    Проверяем два случая:
      1) expires_at в прошлом → продление идёт от now (+duration_days)
      2) expires_at в будущем → продление идёт от будущего expires_at (+duration_days)
    """
    user = TelegramUser.objects.create(user_id=777002566, username="admin_anchor", first_name="AdminAnchor")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    # 1) Первый платёж -> создаёт подписку
    ref1 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref1, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    p1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref1,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-ADM-1",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p1), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE
    first_expire = sub.expires_at

    # === Случай A: админ «урезал» срок в прошлое ===
    past = timezone.now() - timedelta(days=10)
    sub.expires_at = past
    sub.save(update_fields=["expires_at", "updated_at"])

    ref2 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref2, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    p2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref2,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-ADM-2",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p2), content_type="application/json")
    assert r2.status_code == 200

    sub.refresh_from_db()
    now = timezone.now()
    # продление от now
    assert (now + timedelta(days=29, hours=23)) <= sub.expires_at <= (now + timedelta(days=30, hours=1))

    # === Случай B: админ «нарастил» срок в будущее ===
    future_anchor = timezone.now() + timedelta(days=40)
    sub.expires_at = future_anchor
    sub.save(update_fields=["expires_at", "updated_at"])

    ref3 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref3, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    p3 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref3,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-ADM-3",
    }
    r3 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p3), content_type="application/json")
    assert r3.status_code == 200

    sub.refresh_from_db()
    # продление от future_anchor
    assert (future_anchor + timedelta(days=29, hours=23)) <= sub.expires_at <= (future_anchor + timedelta(days=30, hours=1))
