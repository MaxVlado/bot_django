# bot/notifications.py
from datetime import datetime

# SQL для идемпотентности уведомлений об успехе
SQL_NOTIFY_WAS_SENT = """
SELECT 1 FROM bot_payment_notifications
WHERE order_reference = $1
LIMIT 1
"""

SQL_NOTIFY_MARK_SENT = """
INSERT INTO bot_payment_notifications(order_reference, sent_at)
VALUES ($1, now())
"""


async def notify_payment_success(
    pool,
    bot_api,
    user_id: int,
    order_reference: str,
    plan_name: str,
    expires_at: datetime | None = None,
) -> bool:
    """
    Отправляет подтверждение об успешной оплате ровно ОДИН раз на order_reference.
    Возвращает True, если сообщение отправлено сейчас; False, если уже было отправлено ранее.
    """
    try:
        already = await pool.fetchval(SQL_NOTIFY_WAS_SENT, order_reference)
    except Exception:
        already = False

    if already:
        return False

    expires_txt = ""
    if expires_at:
        try:
            expires_txt = f"\nДо: <b>{expires_at.strftime('%d.%m.%Y')}</b>"
        except Exception:
            pass

    text = (
        f"✅ Платёж подтверждён!\n"
        f"Подписка <b>{plan_name}</b> активирована/продлена.{expires_txt}"
    )

    await bot_api.send_message(chat_id=user_id, text=text, parse_mode="HTML")

    try:
        await pool.execute(SQL_NOTIFY_MARK_SENT, order_reference)
    except Exception:
        pass

    return True


async def notify_payment_non_success(
    *,
    bot_api,
    user_id: int,
    order_reference: str,
    status: str,
    reason: str | None = None,
) -> None:
    """
    Информирует пользователя о неуспешных/промежуточных статусах.
    Намеренно НЕ содержит «Платёж подтверждён».
    """
    st = (status or "").upper().strip()

    if st == "DECLINED":
        line = "Оплата отклонена (declined)"
    elif st == "REFUNDED":
        line = "Выполнен возврат платежа (refund)"
    elif st == "EXPIRED":
        line = "Истёк срок оплаты (expired)"
    elif st == "PENDING":
        line = "Платёж в ожидании (pending)"
    elif st == "IN_PROCESS":
        line = "Платёж в обработке (in process)"
    elif st == "WAITING_AUTH_COMPLETE":
        line = "Ожидается подтверждение 3-D Secure (3DS auth)"
    else:
        line = f"Статус платежа: {st or 'unknown'}"

    reason_txt = f"\nПричина: {reason}" if reason else ""
    text = f"ℹ️ {line}.{reason_txt}\nref: {order_reference}"

    await bot_api.send_message(chat_id=user_id, text=text)
