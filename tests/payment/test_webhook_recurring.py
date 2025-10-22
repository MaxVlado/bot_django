# tests/test_webhook_recurring.py
import json
import pytest
from django.utils import timezone
from datetime import timedelta


from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus, VerifiedUser
from tests.scenario_cov import covers


@covers("S5.1", "S13.1")
@pytest.mark.django_db
def test_recurring_first_payment_records_rec_token(client):
    """
    Первый успешный платёж, в вебхуке есть recToken.
    Проверяем:
      - инвойс -> APPROVED и хранит recToken
      - подписка создана и ACTIVE
      - VerifiedUser создан
    (Примечание: перенос recToken в Subscription.card_token можем добавить отдельным шагом.)
    """
    user = TelegramUser.objects.create(user_id=777000888, username="recur1", first_name="Recur")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)
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
        "transactionId": "TX-REC-1",
        "recToken": "tok_first_rec",
        "cardPan": "444455******1111",
        "paymentSystem": "VISA",
        "issuerBankName": "Bank X",
        "issuerBankCountry": "UA",
    }

    resp = client.post(
        "/api/payments/wayforpay/webhook/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "accept"

    # Инвойс
    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.rec_token == "tok_first_rec"
    assert inv.paid_at is not None

    # Подписка
    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE

    # VerifiedUser
    v = VerifiedUser.objects.get(user=user, bot_id=1)
    assert v.successful_payments_count >= 1
    assert v.total_amount_paid >= plan.price


@covers("S5.2")
@pytest.mark.django_db
def test_recurring_followup_extends_subscription_and_updates_token(client):
    """
    Есть активная подписка (создана первым успехом). 
    Приходит следующий рекуррентный APPROVED (orderReference с хвостом _WFPREG-...), с новым recToken.
    Ожидаем:
      - подписка продлена ещё на duration_days
      - subscription.card_token / card_masked обновлены с инвойса
    """
    user = TelegramUser.objects.create(user_id=777000889, username="recur2", first_name="Recur2")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    # 1) Первый успех -> создаём подписку и сразу сохраняем токен карты
    order_ref_1 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=order_ref_1,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,
        currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )
    payload1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_1,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-REC-START",
        "recToken": "tok_first",
        "cardPan": "444455******1111",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload1), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE
    first_expire = sub.expires_at
    # ⚠️ теперь токен сохраняется уже на первом платеже:
    assert sub.card_token == "tok_first"
    assert sub.card_masked == "444455******1111"

    # 2) Рекуррентный APPROVED с новым токеном
    # НЕ создаём новый Invoice! Используем тот же orderReference с суффиксом
    order_ref_2 = f"{order_ref_1}_WFPREG-1"
    
    payload2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_2,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-REC-FOLLOW",
        "recToken": "tok_second",
        "cardPan": "555566******2222",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload2), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Подписка продлена на ещё один период и токен/маска обновлены
    sub.refresh_from_db()
    assert (first_expire + timedelta(days=29, hours=23)) <= sub.expires_at <= (first_expire + timedelta(days=30, hours=1))
    assert sub.card_token == "tok_second"
    assert sub.card_masked == "555566******2222"


@covers("S5.3")
@pytest.mark.django_db
def test_recurring_declined_does_not_extend_and_keeps_token(client):
    """
    Пользователь «отключил автоплатежи» (по факту приходит DECLINED на рекуррентку).
    Ожидаем:
      - подписка остаётся ACTIVE
      - expires_at не меняется
      - card_token / card_masked не меняются
    """
    # 1) создаём подписку: первый успех
    user = TelegramUser.objects.create(user_id=777001666, username="recur_off", first_name="Off")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    order_ref_1 = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv1 = Invoice.objects.create(
        order_reference=order_ref_1, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    payload1 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_1,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-REC-OK-1",
        "recToken": "tok_first",
        "cardPan": "444455******1111",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload1), content_type="application/json")
    assert r1.status_code == 200

    # 2) делаем один успешный рекуррентный платёж, чтобы в подписке появились token/mask
    # НЕ создаём новый Invoice! Используем orderReference с суффиксом
    order_ref_2 = f"{order_ref_1}_WFPREG-a"
    
    payload2 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_2,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-REC-OK-2",
        "recToken": "tok_keep",
        "cardPan": "555566******2222",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload2), content_type="application/json")
    assert r2.status_code == 200

    # фиксация текущего состояния подписки
    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    expires_before = sub.expires_at
    token_before = sub.card_token
    masked_before = sub.card_masked
    assert token_before == "tok_keep"
    assert masked_before == "555566******2222"

    # 3) рекуррентная попытка DECLINED (автоплатёж «отключён/заблокирован»)
    # НЕ создаём новый Invoice! Используем orderReference с суффиксом
    order_ref_3 = f"{order_ref_1}_WFPREG-b"
    
    payload3 = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref_3,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "DECLINED",
        "reasonCode": "autopay_off",
        "transactionId": "TX-REC-DECL",
        "recToken": "tok_keep",  # прислали тот же токен
        "cardPan": "555566******2222",
    }
    r3 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload3), content_type="application/json")
    assert r3.status_code == 200
    assert r3.json().get("status") == "accept"

    # Проверяем, что ничего не поменялось
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.expires_at == expires_before
    assert sub.card_token == token_before
    assert sub.card_masked == masked_before


@covers("S5.4")
@pytest.mark.django_db
def test_recurring_multiple_declines_do_not_extend_and_keep_token(client):
    """
    Несколько подряд DECLINED по рекуррентке:
      - подписка остаётся ACTIVE
      - expires_at не меняется
      - card_token / card_masked не меняются
    """
    # 1) базовая активная подписка с токеном
    user = TelegramUser.objects.create(user_id=777001777, username="recur_dead", first_name="DeadTok")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    # первый успех
    first_ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=first_ref, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    payload_ok = {
        "merchantAccount": "test_merch_n1",
        "orderReference": first_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-REC-OK",
        "recToken": "tok_alive",
        "cardPan": "444455******1111",
    }
    r_ok = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_ok), content_type="application/json")
    assert r_ok.status_code == 200

    # успешная рекуррентка для заполнения токена в подписке
    # НЕ создаём новый Invoice! Используем orderReference с суффиксом
    ref_reg_ok = f"{first_ref}_WFPREG-x"
    
    payload_reg_ok = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref_reg_ok,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-REC-OK2",
        "recToken": "tok_keep_me",
        "cardPan": "555566******2222",
    }
    r_reg_ok = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_reg_ok), content_type="application/json")
    assert r_reg_ok.status_code == 200

    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    expires_before = sub.expires_at
    token_before = sub.card_token
    masked_before = sub.card_masked
    assert token_before == "tok_keep_me"

    # 2) три подряд DECLINED по рекуррентке
    # НЕ создаём новые Invoice! Используем orderReference с суффиксами
    for suffix in ("d1", "d2", "d3"):
        ref_decl = f"{first_ref}_WFPREG-{suffix}"
        
        payload_decl = {
            "merchantAccount": "test_merch_n1",
            "orderReference": ref_decl,
            "amount": int(plan.price),
            "currency": plan.currency,
            "transactionStatus": "DECLINED",
            "reasonCode": "insufficient_funds",
            "transactionId": f"TX-REC-DECL-{suffix}",
            "recToken": "tok_keep_me",
            "cardPan": "555566******2222",
        }
        r_decl = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_decl), content_type="application/json")
        assert r_decl.status_code == 200
        assert r_decl.json().get("status") == "accept"

    # Проверяем: ничего не поменялось
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.expires_at == expires_before
    assert sub.card_token == token_before
    assert sub.card_masked == masked_before


@covers("S6.3")
@pytest.mark.django_db
def test_recurring_refunded_does_not_extend_and_keeps_token(client):
    """
    После успешного платежа с токеном:
      - приходит рекуррентный REFUNDED по другому инвойсу (_WFPREG-...).
    Ожидаем:
      - подписка НЕ продлевается
      - card_token / card_masked НЕ меняются
      - статус того инвойса не понижается до REFUNDED (остаётся как был, у нас это PENDING),
        т.к. политика — не даунгрейдить и не трогать подписку.
    """
    user = TelegramUser.objects.create(user_id=777003001, username="ref_rec", first_name="RefRec")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    # 1) Базовый APPROVED → создаём подписку и сохраняем токен
    ref_ok = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref_ok, user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency, payment_status=PaymentStatus.PENDING,
    )
    payload_ok = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref_ok,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-REC-OK",
        "recToken": "tok_keep",
        "cardPan": "444455******1111",
    }
    r1 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_ok), content_type="application/json")
    assert r1.status_code == 200

    sub = Subscription.objects.get(user=user, bot_id=1)
    first_expire = sub.expires_at
    assert sub.card_token == "tok_keep"
    assert sub.card_masked == "444455******1111"

    # 2) Рекуррентный инвойс, который WFP помечает REFUNDED (или REVERSED/CHARGEBACK)
    # НЕ создаём новый Invoice! Используем orderReference с суффиксом
    ref_refund = f"{ref_ok}_WFPREG-r"
    
    payload_refund = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref_refund,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "REFUNDED",
        "reasonCode": "reversal",
        "transactionId": "TX-REC-REFUNDED",
        "recToken": "tok_new_should_not_apply",
        "cardPan": "555566******2222",
    }
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload_refund), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Проверяем, что подписка не продлилась и токен/маска не изменились
    sub.refresh_from_db()
    assert sub.expires_at == first_expire
    assert sub.card_token == "tok_keep"
    assert sub.card_masked == "444455******1111"