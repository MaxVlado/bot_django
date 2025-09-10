# tests/test_multibot.py
import json
import pytest
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers


@covers("S12.1")
@pytest.mark.django_db
def test_same_user_two_bots_independent_subscriptions(client):
    """
    У одного TelegramUser две подписки на РАЗНЫХ ботах.
    APPROVED по боту #1 не влияет на подписку бота #2 и наоборот.
    """
    user = TelegramUser.objects.create(user_id=777002444, username="multi_bot", first_name="MultiBot")

    plan_b1 = Plan.objects.create(bot_id=1, name="Plan-30-B1", price=10, currency="UAH", duration_days=30, enabled=True)
    plan_b2 = Plan.objects.create(bot_id=2, name="Plan-30-B2", price=15, currency="UAH", duration_days=30, enabled=True)

    # Инвойс под бота #1
    ref1 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan_b1.id)
    Invoice.objects.create(
        order_reference=ref1, user=user, plan=plan_b1, bot_id=1,
        amount=plan_b1.price, currency=plan_b1.currency, payment_status=PaymentStatus.PENDING,
    )

    # Инвойс под бота #2
    ref2 = Invoice.generate_order_reference(bot_id=2, user_id=user.user_id, plan_id=plan_b2.id)
    Invoice.objects.create(
        order_reference=ref2, user=user, plan=plan_b2, bot_id=2,
        amount=plan_b2.price, currency=plan_b2.currency, payment_status=PaymentStatus.PENDING,
    )

    # 1) Приходит APPROVED по боту #1
    p1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref1,
        "amount": int(plan_b1.price),
        "currency": plan_b1.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-B1",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p1), content_type="application/json")
    assert r1.status_code == 200

    # Проверяем: есть активная подписка только у бота #1
    sub_b1 = Subscription.objects.get(user=user, plan=plan_b1, bot_id=1)
    assert sub_b1.status == SubscriptionStatus.ACTIVE
    assert not Subscription.objects.filter(user=user, plan=plan_b2, bot_id=2).exists()

    # 2) Теперь APPROVED по боту #2
    p2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref2,
        "amount": int(plan_b2.price),
        "currency": plan_b2.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-B2",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(p2), content_type="application/json")
    assert r2.status_code == 200

    # Обе подписки активны и не мешают друг другу
    sub_b1.refresh_from_db()
    sub_b2 = Subscription.objects.get(user=user, plan=plan_b2, bot_id=2)
    assert sub_b1.status == SubscriptionStatus.ACTIVE
    assert sub_b2.status == SubscriptionStatus.ACTIVE
    assert sub_b1.bot_id != sub_b2.bot_id

@covers("S12.2")
@pytest.mark.django_db
def test_second_plan_same_bot_does_not_create_second_subscription(client):
    """
    У пользователя уже есть активная подписка на бота #1 (plan A).
    Пользователь оплачивает другой план того же бота (plan B).
    Ожидаем (текущая политика и реализация):
      - второй инвойс APPROVED (деньги списаны)
      - НО новая подписка не создаётся (всё ещё 1 активная подписка у этого бота)
      - подписка остаётся на исходном плане (plan A)
    """
    user = TelegramUser.objects.create(user_id=777002445, username="one_bot_one_sub", first_name="OneSub")

    plan_a = Plan.objects.create(bot_id=1, name="Plan-A", price=10, currency="UAH", duration_days=30, enabled=True)
    plan_b = Plan.objects.create(bot_id=1, name="Plan-B", price=15, currency="UAH", duration_days=30, enabled=True)

    # 1) Инвойс по plan A -> APPROVED -> создаётся активная подписка
    ref_a = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan_a.id)
    Invoice.objects.create(
        order_reference=ref_a, user=user, plan=plan_a, bot_id=1,
        amount=plan_a.price, currency=plan_a.currency, payment_status=PaymentStatus.PENDING,
    )
    payload_a = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref_a,
        "amount": int(plan_a.price),
        "currency": plan_a.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-A",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_a), content_type="application/json")
    assert r1.status_code == 200

    # Проверка: есть одна активная подписка (plan A)
    subs_bot1 = Subscription.objects.filter(user=user, bot_id=1)
    assert subs_bot1.count() == 1
    sub = subs_bot1.first()
    assert sub.plan_id == plan_a.id
    assert sub.status == SubscriptionStatus.ACTIVE

    # 2) Инвойс по plan B -> APPROVED
    ref_b = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan_b.id)
    Invoice.objects.create(
        order_reference=ref_b, user=user, plan=plan_b, bot_id=1,
        amount=plan_b.price, currency=plan_b.currency, payment_status=PaymentStatus.PENDING,
    )
    payload_b = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref_b,
        "amount": int(plan_b.price),
        "currency": plan_b.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-B",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_b), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Итог: второй инвойс оплачен, но в рамках одного бота остаётся ровно 1 подписка — та же (plan A)
    inv_b = Invoice.objects.get(order_reference=ref_b)
    assert inv_b.payment_status == PaymentStatus.APPROVED

    subs_bot1 = Subscription.objects.filter(user=user, bot_id=1)
    assert subs_bot1.count() == 1, "не должно появиться второй подписки у того же бота"
    assert subs_bot1.first().plan_id == plan_a.id, "активной остаётся подписка исходного плана"
