# tests/test_idempotency_race.py
import pytest
from tests.scenario_cov import covers

import threading
from datetime import timedelta
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription
from payments.models import Invoice, PaymentStatus
from django.db import connections

# динамический импорт сервиса
import importlib
mod = None
for p in ("wayforpay.services", "payments.wayforpay.services"):
    try:
        mod = importlib.import_module(p)
        break
    except ImportError:
        continue
assert mod is not None, "WayForPayService module not found"
WayForPayService = getattr(mod, "WayForPayService")


@covers("S9.3")
@pytest.mark.django_db(transaction=True)  # важно для многопоточности
def test_concurrent_webhooks_for_same_reference_apply_only_once():
    """
    Два параллельных вызова обработчика по одному и тому же orderReference.
    Ожидаем:
      - инвойс становится APPROVED
      - подписка создана/продлена ровно один раз
    """
    user = TelegramUser.objects.create(user_id=777004660, username="race", first_name="Race")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    Invoice.objects.create(
        order_reference=ref,
        user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    payload = {
        "merchantAccount": "test_merch_n1",
        "orderReference": ref,
        "amount": int(plan.price),
        "currency": plan.currency,
        "transactionStatus": "APPROVED",
        "reasonCode": "1100",
        "transactionId": "TX-RACE",
    }

    svc = WayForPayService()

    errs = []

    def worker():
        try:
            svc.process_payment_response(payload)
        except Exception as e:
            errs.append(e)
        finally:
            # важно: закрыть соединение, созданное в этом потоке
            connections.close_all()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errs, f"exceptions in threads: {errs}"

    inv = Invoice.objects.get(order_reference=ref)
    assert inv.payment_status == PaymentStatus.APPROVED
    assert inv.paid_at is not None

    subs = Subscription.objects.filter(user=user, bot_id=1)
    assert subs.count() == 1

    sub = subs.first()
    now = timezone.now()
    assert (now + timedelta(days=29, hours=23)) <= sub.expires_at <= (now + timedelta(days=30, hours=1))
