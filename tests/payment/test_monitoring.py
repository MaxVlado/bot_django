# tests/test_monitoring.py
import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan
from payments.models import Invoice, PaymentStatus
from tests.scenario_cov import covers

# динамический импорт utils (поддержка разных путей)
import importlib
mod = None
for p in ("payments.monitoring",):
    try:
        mod = importlib.import_module(p)
        break
    except ImportError:
        continue
assert mod is not None, "payments.monitoring module not found"
decline_stats = getattr(mod, "decline_stats")
is_decline_rate_high = getattr(mod, "is_decline_rate_high")

# динамический импорт мониторинга (повторно использовать можно)
mod = importlib.import_module("payments.monitoring")
find_fast_success_bursts = getattr(mod, "find_fast_success_bursts")
has_fast_success_bursts = getattr(mod, "has_fast_success_bursts")

@covers("S17.1")
@pytest.mark.django_db
def test_decline_ratio_high_for_recent_window():
    """
    За последний час доля DECLINED > 60% -> триггерим высокий процент отказов.
    """
    user = TelegramUser.objects.create(user_id=777004001, username="mon", first_name="Mon")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    now = timezone.now()

    def mk(order_ref, status, notified_offset_min=0):
        inv = Invoice.objects.create(
            order_reference=order_ref,
            user=user, plan=plan, bot_id=1,
            amount=plan.price, currency=plan.currency,
            payment_status=status,
        )
        inv.notified_at = now - timedelta(minutes=notified_offset_min)
        inv.save(update_fields=["notified_at", "updated_at"])
        return inv

    # 10 инвойсов в окне: 6 DECLINED, 4 APPROVED
    for i in range(6):
        mk(f"REF-D-{i}", PaymentStatus.DECLINED, notified_offset_min=5)
    for i in range(4):
        mk(f"REF-A-{i}", PaymentStatus.APPROVED, notified_offset_min=7)

    # и один старый DECLINED за пределами окна (не должен считаться)
    mk("REF-OLD-D", PaymentStatus.DECLINED, notified_offset_min=180)

    stats = decline_stats(window_minutes=60, bot_id=1)
    assert stats["total"] == 10
    assert stats["declined"] == 6
    assert abs(stats["ratio"] - 0.6) < 1e-6

    # порог 50% -> True; порог 70% -> False
    assert is_decline_rate_high(threshold=0.5, window_minutes=60, bot_id=1) is True
    assert is_decline_rate_high(threshold=0.7, window_minutes=60, bot_id=1) is False



@covers("S17.2")
@pytest.mark.django_db
def test_fast_success_bursts_from_single_user_are_detected():
    """
    За последние 5 минут один и тот же пользователь сделал >= threshold успешных оплат.
    Ожидаем: детектор вернёт этого пользователя.
    """
    user1 = TelegramUser.objects.create(user_id=777004111, username="burst", first_name="Burst")
    user2 = TelegramUser.objects.create(user_id=777004112, username="other", first_name="Other")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    now = timezone.now()

    def mk(u, ref, minutes_ago=1):
        inv = Invoice.objects.create(
            order_reference=ref,
            user=u, plan=plan, bot_id=1,
            amount=plan.price, currency=plan.currency,
            payment_status=PaymentStatus.APPROVED,
        )
        inv.notified_at = now - timedelta(minutes=minutes_ago)
        inv.save(update_fields=["notified_at", "updated_at"])
        return inv

    # user1 — 4 быстрых APPROVED в окне (порог будет 3)
    for i in range(4):
        mk(user1, f"REF-U1-{i}", minutes_ago=2)

    # user2 — 2 APPROVED (ниже порога)
    for i in range(2):
        mk(user2, f"REF-U2-{i}", minutes_ago=3)

    # один старый (вне окна) — не должен учитываться
    inv_old = Invoice.objects.create(
        order_reference="REF-OLD",
        user=user1, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.APPROVED,
    )
    inv_old.notified_at = now - timedelta(minutes=90)
    inv_old.save(update_fields=["notified_at", "updated_at"])

    offenders = find_fast_success_bursts(window_minutes=5, threshold=3, bot_id=1)
    tg_ids = {o["tg_user_id"] for o in offenders}
    assert user1.user_id in tg_ids
    assert user2.user_id not in tg_ids

    assert has_fast_success_bursts(window_minutes=5, threshold=3, bot_id=1) is True
    assert has_fast_success_bursts(window_minutes=5, threshold=5, bot_id=1) is False


find_amount_currency_mismatches = getattr(mod, "find_amount_currency_mismatches")
has_amount_currency_mismatches = getattr(mod, "has_amount_currency_mismatches")


@covers("S17.3")
@pytest.mark.django_db
def test_amount_currency_mismatch_is_detected_in_window():
    """
    В окне мониторинга есть инвойс, где raw_response_payload.amount/currency
    отличаются от invoice.amount/currency — считаем это расхождением.
    """
    user = TelegramUser.objects.create(user_id=777004222, username="mm", first_name="MM")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    now = timezone.now()

    # 1) Инвойс с МИССМАТЧЕМ (amount из вебхука = 9, а в инвойсе 10)
    inv_bad = Invoice.objects.create(
        order_reference="REF-MM-1",
        user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )
    inv_bad.raw_response_payload = {"amount": 9, "currency": "UAH"}
    inv_bad.notified_at = now - timedelta(minutes=5)
    inv_bad.save(update_fields=["raw_response_payload", "notified_at", "updated_at"])

    # 2) Инвойс БЕЗ расхождения (совпадают)
    inv_ok = Invoice.objects.create(
        order_reference="REF-MM-2",
        user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )
    inv_ok.raw_response_payload = {"amount": int(plan.price), "currency": plan.currency}
    inv_ok.notified_at = now - timedelta(minutes=7)
    inv_ok.save(update_fields=["raw_response_payload", "notified_at", "updated_at"])

    # 3) Старый (вне окна) — даже с mismatch не учитывается
    inv_old = Invoice.objects.create(
        order_reference="REF-MM-OLD",
        user=user, plan=plan, bot_id=1,
        amount=plan.price, currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )
    inv_old.raw_response_payload = {"amount": 8, "currency": "USD"}
    inv_old.notified_at = now - timedelta(minutes=180)
    inv_old.save(update_fields=["raw_response_payload", "notified_at", "updated_at"])

    rows = find_amount_currency_mismatches(window_minutes=60, bot_id=1)
    refs = {r["order_reference"] for r in rows}
    assert "REF-MM-1" in refs
    assert "REF-MM-2" not in refs
    assert "REF-MM-OLD" not in refs

    # Порог по количеству (>= 1) — True
    assert has_amount_currency_mismatches(threshold_count=1, window_minutes=60, bot_id=1) is True
    # Порог 2 — False (в окне только один mismatch)
    assert has_amount_currency_mismatches(threshold_count=2, window_minutes=60, bot_id=1) is False
