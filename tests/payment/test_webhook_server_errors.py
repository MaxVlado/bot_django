# tests/test_webhook_server_errors.py
import json
import pytest
import importlib

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers

from django.db import utils as db_utils


@covers("S10.1")
@pytest.mark.django_db
def test_first_request_500_then_retry_200_processes_once(client, monkeypatch):
    """
    Эмулируем: первый вызов WebhookView.post бросает исключение (наш 5xx),
    WayForPay ретраит тот же payload → повтор успешный и обрабатывается ровно один раз.
    """

    # Подготовка БД
    user = TelegramUser.objects.create(user_id=777002333, username="srv5xx", first_name="Srv")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    order_ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
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
        "transactionId": "TX-ON-RETRY",
    }

    # Динамически импортируем модуль с вьюхой (работает и для wayforpay.*, и для payments.wayforpay.*)
    mod = None
    for p in ("wayforpay.views", "payments.wayforpay.views"):
        try:
            mod = importlib.import_module(p)
            break
        except ImportError:
            continue
    assert mod is not None, "WebhookView module not found; ensure you have wayforpay/views.py"
    WebhookView = getattr(mod, "WebhookView")

    # Патчим post: 1-й вызов → исключение, далее → оригинальная логика
    original_post = WebhookView.post
    calls = {"n": 0}

    def flaky_post(self, request, *args, **kwargs):
        if calls["n"] == 0:
            calls["n"] += 1
            raise RuntimeError("Simulated 5xx on first attempt")
        return original_post(self, request, *args, **kwargs)

    monkeypatch.setattr(WebhookView, "post", flaky_post)

    # 1) Первый запрос → исключение (в тест-клиенте поднимается, а не 500)
    with pytest.raises(RuntimeError):
        client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")

    # 2) Ретрай тем же payload → 200 'accept' и реальная обработка
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    # Проверяем состояние: оплачен и активировано один раз
    inv = Invoice.objects.get(order_reference=order_ref)
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.paid_at is not None

    sub = Subscription.objects.get(user=user, plan=plan, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE

    # Дополнительно: ещё один ретрай тем же orderReference ничего не меняет (идемпотентность)
    r3 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r3.status_code == 200
    inv.refresh_from_db()
    sub.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED




@covers("S10.2")
@pytest.mark.django_db
def test_db_error_first_then_retry_processes_once(client, monkeypatch):
    """
    Имитация: на первом вебхуке падаем db OperationalError внутри сервисной обработки,
    WFP ретраит тот же payload → второй запрос проходит и выполняет изменения ровно один раз.
    Первый ответ от нашего сервиса — 200 'accept' со статусом 'decline' (как у нас реализовано).
    """
    # Подготовка
    user = TelegramUser.objects.create(user_id=777002334, username="srvdb", first_name="SrvDB")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=5, currency="UAH", duration_days=30, enabled=True)

    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
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
        "transactionId": "TX-ON-RETRY-DB",
    }

    # Динамически импортируем сервис и патчим process_payment_response:
    # 1-й вызов → OperationalError, далее → оригинальный метод
    mod = None
    for p in ("wayforpay.services", "payments.wayforpay.services"):
        try:
            mod = importlib.import_module(p)
            break
        except ImportError:
            continue
    assert mod is not None, "WayForPayService module not found"
    WayForPayService = getattr(mod, "WayForPayService")
    original_proc = WayForPayService.process_payment_response
    calls = {"n": 0}

    def flaky_proc(self, response_data, *args, **kwargs):
        if calls["n"] == 0:
            calls["n"] += 1
            raise db_utils.OperationalError("Simulated DB down")
        return original_proc(self, response_data, *args, **kwargs)

    monkeypatch.setattr(WayForPayService, "process_payment_response", flaky_proc)

    # 1) Первый вебхук: падаем OperationalError → это моделирует наш 5xx
    with pytest.raises(db_utils.OperationalError):
        client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")


    inv = Invoice.objects.get(order_reference=ref)
    assert inv.payment_status == PaymentStatus.PENDING
    assert inv.paid_at is None
    assert not Subscription.objects.filter(user=user, bot_id=1).exists()

    # 2) Ретрай тем же payload: теперь проходит и применяет изменения один раз
    r2 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r2.status_code == 200
    assert r2.json().get("status") == "accept"

    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.paid_at is not None
    sub = Subscription.objects.get(user=user, bot_id=1)
    assert sub.status == SubscriptionStatus.ACTIVE

    # 3) Доп. ретрай тем же payload: идемпотентность — состояния не меняются
    r3 = client.post("/api/payments/wayforpay/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r3.status_code == 200
    inv_after = Invoice.objects.get(order_reference=ref)
    assert inv_after.payment_status == PaymentStatus.APPROVED
