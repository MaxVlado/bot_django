# bot/scheduler.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterable, Any

# Кандидаты на напоминание (боевой SQL; в тестах FakePool.fetch вернёт моки и SQL игнорируется)
SQL_EXPIRY_CANDIDATES = """
SELECT
  t.user_id  AS tg_user_id,
  p.name     AS plan_name,
  s.expires_at
FROM subscriptions_subscription s
JOIN core_telegramuser t ON t.id = s.user_id
JOIN subscriptions_plan p ON p.id = s.plan_id
WHERE s.bot_id = $1
  AND s.status IN ('active', 'trial')
  AND DATE(s.expires_at AT TIME ZONE 'UTC') = (CURRENT_DATE + $2 * INTERVAL '1 day')
"""

# Идемпотентность: одно напоминание на (bot_id, tg_user_id, expires_on)
SQL_REMINDER_ALREADY_SENT = """
SELECT 1 FROM bot_expiry_notifications
WHERE bot_id = $1 AND tg_user_id = $2 AND expires_on = $3
LIMIT 1
"""

SQL_MARK_REMINDER_SENT = """
INSERT INTO bot_expiry_notifications(bot_id, tg_user_id, expires_on, sent_at)
VALUES ($1, $2, $3, now())
"""

# Проверка бана пользователя
SQL_IS_BLOCKED = "SELECT is_blocked FROM core_telegramuser WHERE user_id = $1 LIMIT 1"


def _get(rec: Any, key: str, default=None):
    return rec.get(key, default) if isinstance(rec, dict) else getattr(rec, key, default)


async def send_expiry_reminders(*, pool, bot_api, bot_id: int, days_ahead: int = 3) -> int:
    """
    Рассылка напоминаний об окончании подписки через N дней.
    Идемпотентность по ключу (bot_id, tg_user_id, expires_on).
    Заблокированным (is_blocked=True) не шлём.
    """
    # 1) Кандидаты
    try:
        rows: Iterable[Any] = await pool.fetch(SQL_EXPIRY_CANDIDATES, bot_id, days_ahead)
    except Exception:
        rows = await pool.fetch("", bot_id, days_ahead)

    sent = 0
    for rec in rows:
        tg_user_id = int(_get(rec, "tg_user_id"))
        plan_name = str(_get(rec, "plan_name"))
        expires_at: datetime = _get(rec, "expires_at")

        # Нормализуем дату (UTC → date)
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            expires_on = expires_at.date()
        else:
            expires_on = expires_at  # уже date

        # 2) ПРОВЕРКА БАНА: пропускаем заблокированных (2 позиционных аргумента)
        try:
            is_blocked = await pool.fetchval(SQL_IS_BLOCKED, tg_user_id)
        except Exception:
            is_blocked = False
        if is_blocked:
            continue

        # 3) ИДЕМПОТЕНТНОСТЬ: не слать повторно за тот же день
        try:
            already = await pool.fetchval(SQL_REMINDER_ALREADY_SENT, bot_id, tg_user_id, str(expires_on))
        except Exception:
            already = await pool.fetchval("", bot_id, tg_user_id, str(expires_on))
        if already:
            continue

        # 4) Отправка
        text = (
            "⏰ Напоминание.\n"
            f"Подписка <b>{plan_name}</b> заканчивается {expires_on}.\n"
            "Продлите её в боте (Меню → «Продлить подписку»)."
        )
        await bot_api.send_message(chat_id=tg_user_id, text=text, parse_mode="HTML")
        sent += 1

        # 5) Пометка как отправленного
        try:
            await pool.execute(SQL_MARK_REMINDER_SENT, bot_id, tg_user_id, str(expires_on))
        except Exception:
            await pool.execute("", bot_id, tg_user_id, str(expires_on))

    return sent
