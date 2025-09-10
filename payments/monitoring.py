# payments/monitoring.py
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, F

from .models import Invoice, PaymentStatus


def decline_stats(window_minutes: int = 60, bot_id: int | None = None) -> dict:
    """
    Статистика отказов за последнее окно (по notified_at):
      - total: всего инвойсов с вебхуком в окне
      - declined: кол-во со статусом DECLINED
      - ratio: доля DECLINED (0..1)
    """
    since = timezone.now() - timedelta(minutes=window_minutes)
    qs = Invoice.objects.filter(notified_at__gte=since)
    if bot_id is not None:
        qs = qs.filter(bot_id=bot_id)

    total = qs.count()
    declined = qs.filter(payment_status=PaymentStatus.DECLINED).count()
    ratio = (declined / total) if total else 0.0
    return {"total": total, "declined": declined, "ratio": ratio}


def is_decline_rate_high(*, threshold: float = 0.5, window_minutes: int = 60, bot_id: int | None = None) -> bool:
    """
    True, если доля DECLINED в окне >= threshold.
    """
    stats = decline_stats(window_minutes=window_minutes, bot_id=bot_id)
    return stats["ratio"] >= float(threshold)


def find_fast_success_bursts(*, window_minutes: int = 5, threshold: int = 3, bot_id: int | None = None):
    """
    Найти пользователей, у которых за последнее окно >= threshold успешных оплат.
    Возвращает список словарей: {'user_db_id', 'tg_user_id', 'count'}.
    """
    since = timezone.now() - timedelta(minutes=window_minutes)
    qs = Invoice.objects.filter(
        notified_at__gte=since,
        payment_status=PaymentStatus.APPROVED,
    )
    if bot_id is not None:
        qs = qs.filter(bot_id=bot_id)

    rows = (
        qs.values("user_id", "user__user_id")
          .annotate(cnt=Count("id"))
          .filter(cnt__gte=threshold)
    )
    return [
        {"user_db_id": r["user_id"], "tg_user_id": r["user__user_id"], "count": r["cnt"]}
        for r in rows
    ]


def has_fast_success_bursts(*, window_minutes: int = 5, threshold: int = 3, bot_id: int | None = None) -> bool:
    """
    True, если есть хотя бы один пользователь с >= threshold успешных оплат за окно.
    """
    return len(find_fast_success_bursts(window_minutes=window_minutes, threshold=threshold, bot_id=bot_id)) > 0


def find_amount_currency_mismatches(*, window_minutes: int = 60, bot_id: int | None = None):
    """
    Ищет инвойсы за окно времени, у которых amount/currency из raw_response_payload
    не совпадают с amount/currency инвойса.
    Возвращает список словарей с деталями.
    """
    since = timezone.now() - timedelta(minutes=window_minutes)
    qs = Invoice.objects.filter(notified_at__gte=since)
    if bot_id is not None:
        qs = qs.filter(bot_id=bot_id)

    out = []
    for inv in qs.only("id", "order_reference", "amount", "currency", "raw_response_payload"):
        payload = inv.raw_response_payload or {}
        p_amount = payload.get("amount")
        p_currency = payload.get("currency")
        try:
            inv_amount_int = int(inv.amount)
        except (TypeError, ValueError):
            inv_amount_int = None
        try:
            p_amount_int = int(p_amount) if p_amount is not None else None
        except (TypeError, ValueError):
            p_amount_int = None

        mismatch = (p_amount_int is not None and inv_amount_int is not None and p_amount_int != inv_amount_int) \
                   or (p_currency is not None and str(p_currency).upper() != str(inv.currency).upper())
        if mismatch:
            out.append({
                "invoice_id": inv.id,
                "order_reference": inv.order_reference,
                "invoice_amount": inv_amount_int,
                "payload_amount": p_amount_int,
                "invoice_currency": str(inv.currency).upper() if inv.currency else None,
                "payload_currency": str(p_currency).upper() if p_currency is not None else None,
            })
    return out


def has_amount_currency_mismatches(*, threshold_count: int = 1, window_minutes: int = 60, bot_id: int | None = None) -> bool:
    """
    True, если найдено как минимум threshold_count расхождений суммы/валюты за окно.
    """
    return len(find_amount_currency_mismatches(window_minutes=window_minutes, bot_id=bot_id)) >= int(threshold_count)