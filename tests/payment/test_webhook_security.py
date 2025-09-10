# tests/test_webhook_security.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone


from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers
from payments.wayforpay.api import WayForPayAPI


@covers("S7.1")
@pytest.mark.django_db
def test_invalid_signature_is_ignored(client, settings):
    """
    При включённой проверке подписи:
    - если merchantSignature отсутствует/неверна, вебхук принимаем ('accept'), но
      инвойс и подписку НЕ изменяем.
    """
    # Включаем строгую валидацию на время теста
    settings.WAYFORPAY_VERIFY_SIGNATURE = True

    # Подготовка: пользователь, план, инвойс (PENDING)
    user = TelegramUser.objects.create(user_id=777000666, username="sec", first_name="Sec")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=7, currency="UAH", duration_days=30, enabled=True)
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

    # Действие: шлём APPROVED БЕЗ merchantSignature (нарочно неверная подпись)
    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-BAD-SIGN",
        # "merchantSignature": отсутствует -> validate_response_signature -> False
    }
    resp = client.post(
        "/api/payments/wayforpay/webhook/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "accept"  # ACK отсылаем, но состояние не меняем

    # Проверки: инвойс и подписка без изменений
    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.PENDING
    assert inv.paid_at is None
    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()


@covers("S7.2")
@pytest.mark.django_db
def test_foreign_merchant_account_is_ignored(client, settings):
    """
    Включена проверка: payload с валидной подписью, но merchantAccount чужой.
    Ожидаем: ACK 'accept', но инвойс/подписка НЕ меняются.
    """
    settings.WAYFORPAY_VERIFY_SIGNATURE = True

    user = TelegramUser.objects.create(user_id=777000777, username="foreign", first_name="Merch")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=7, currency="UAH", duration_days=30, enabled=True)
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

    # merchantAccount умышленно другой, но подпись делаем корректную по этим данным
    payload = {
        "merchantAccount": "someone_else_merch",
        "orderReference": order_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-BAD-MERCH",
    }
    wfp = WayForPayAPI()
    payload["merchantSignature"] = wfp.get_response_signature(payload)

    resp = client.post(
        "/api/payments/wayforpay/webhook/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.PENDING
    assert inv.paid_at is None
    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()

@covers("S7.3")
@pytest.mark.django_db
def test_missing_order_reference_is_accepted_without_changes(client, settings):
    """
    Вебхук пришёл с валидным JSON, но без поля orderReference.
    Ожидаем: сервис отвечает ACK 'accept', но инвойсы/подписки не меняются.
    """
    # независимо от флага подписи — payload валидный, но неполный
    settings.WAYFORPAY_VERIFY_SIGNATURE = True

    # Подготовка: создадим любые сущности, чтобы убедиться, что они не меняются
    user = TelegramUser.objects.create(user_id=777000901, username="no_ref", first_name="NoRef")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=7, currency="UAH", duration_days=30, enabled=True)

    payload = {
        "merchantAccount": "test_merch_n1",
        # "orderReference": отсутствует
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-NO-REF",
    }

    resp = client.post(
        "/api/payments/wayforpay/webhook/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "accept"

    # Проверяем, что никаких новых инвойсов/подписок не появилось
    assert not Invoice.objects.filter(user=user, plan=plan, bot_id=1).exists()
    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()

@covers("S7.4")
@pytest.mark.django_db
def test_rate_limit_by_ip(client, settings):
    """
    Делаем 3 запроса подряд -> 200, 4-й -> 429 (перекрыт лимитом).
    """
    # включаем троттлинг и подключаем middleware только на время теста
    settings.WAYFORPAY_RATELIMIT_ENABLED = True
    settings.WAYFORPAY_RATELIMIT_COUNT = 3
    settings.WAYFORPAY_RATELIMIT_WINDOW = 60

    # динамически находим, где лежит WebhookRateLimitMiddleware
    import importlib
    module_path = None
    for p in ("wayforpay.middleware", "payments.wayforpay.middleware"):
        try:
            importlib.import_module(p)
            module_path = p
            break
        except ImportError:
            continue
    assert module_path, "WebhookRateLimitMiddleware module not found; ensure you created wayforpay/middleware.py"

    settings.MIDDLEWARE = [*settings.MIDDLEWARE, f"{module_path}.WebhookRateLimitMiddleware"]

    # локальный кэш для окна
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "rate-limit-test"
        }
    }
    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": "nonexistent-ref",  # не важно: middleware срабатывает раньше вьюхи
        "amount": 1,
        "currency": "UAH",
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-RL",
    }

    import json
    url = "/api/payments/wayforpay/webhook/"
    for i in range(3):
        r = client.post(url, data=json.dumps(payload), content_type="application/json")
        assert r.status_code == 200, f"unexpected status on #{i+1}: {r.status_code}"
    r4 = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert r4.status_code == 429
    assert r4.json().get("error") == "rate_limited"

@covers("S7.5")
@pytest.mark.django_db
def test_replay_old_webhook_is_ignored_by_ttl(client, settings):
    """
    Ставим TTL=1 день. Присылаем APPROVED с processingDate 10 дней назад.
    Ожидаем: ACK 'accept', но инвойс/подписка не меняются.
    """
    settings.WAYFORPAY_VERIFY_SIGNATURE = False  # для удобства теста
    settings.WAYFORPAY_WEBHOOK_TTL_SECONDS = 24 * 3600  # 1 день

    user = TelegramUser.objects.create(user_id=777001222, username="ttl", first_name="TTL")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=7, currency="UAH", duration_days=30, enabled=True)
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

    old_ts = int((timezone.now() - timedelta(days=10)).timestamp())
    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": order_ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-OLD",
        "processingDate": old_ts,
    }

    import json
    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.PENDING, "старый вебхук не должен менять состояние"
    assert inv.paid_at is None
    assert not Subscription.objects.filter(user=user, plan=plan, bot_id=1).exists()

@covers("S8.1")
@pytest.mark.django_db
def test_order_reference_not_found_ack_without_state_change(client):
    """
    Вебхук пришёл с несуществующим orderReference.
    Ожидаем: отвечаем 'accept', инвойсы/подписки не меняются.
    """
    # никаких предварительных инвойсов не создаём
    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": "does-not-exist-REF",
        "amount": 1,
        "currency": "UAH",
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-NOT-FOUND",
    }

    import json
    r = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200
    assert r.json().get("status") == "accept"

    # убеждаемся, что в БД не появился инвойс/подписка "магически"
    from payments.models import Invoice
    from subscriptions.models import Subscription
    assert not Invoice.objects.filter(order_reference="does-not-exist-REF").exists()
    assert Subscription.objects.count() == 0


