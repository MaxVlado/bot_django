"""
B8.1 — Рассылка напоминания об окончании подписки за N дней: сообщение отправлено один раз.

Ожидание:
- send_expiry_reminders рассылает ДМ всем кандидатам с окончанием через N дней.
- Повторный вызов в тот же день НЕ шлёт дубликаты (идемпотентно).
- Возвращает количество отправленных сообщений.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.scheduler import send_expiry_reminders  # noqa: E402


class FakeBotAPI:
    """Минимальный мок Telegram Bot API."""
    def __init__(self):
        self.sent = []  # (chat_id, text)

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.sent.append((chat_id, text))


class FakePool:
    """
    Мок asyncpg.Pool для напоминалок.
    Поддерживает:
      - fetch(sql, bot_id, days_ahead) -> список кандидатов
      - fetchval(sql, bot_id, tg_user_id, expires_on) -> True/False (уже уведомляли)
      - execute(sql, bot_id, tg_user_id, expires_on) -> пометить как отправленное
    """
    def __init__(self, rows):
        self._rows = list(rows)
        self._marked = set()  # ключ: (bot_id, tg_user_id, expires_on_date)

    async def fetch(self, *_args, **_kwargs):
        return self._rows

    async def fetchval(self, *_args, **kwargs):
        # принимаем позиционные: (sql, bot_id, tg_user_id, expires_on)
        if len(_args) >= 4:
            _, bot_id, tg_user_id, expires_on = _args[:4]
        else:
            bot_id = kwargs.get("bot_id")
            tg_user_id = kwargs.get("tg_user_id")
            expires_on = kwargs.get("expires_on")
        key = (int(bot_id), int(tg_user_id), str(expires_on))
        return key in self._marked

    async def execute(self, *_args, **kwargs):
        if len(_args) >= 4:
            _, bot_id, tg_user_id, expires_on = _args[:4]
        else:
            bot_id = kwargs.get("bot_id")
            tg_user_id = kwargs.get("tg_user_id")
            expires_on = kwargs.get("expires_on")
        key = (int(bot_id), int(tg_user_id), str(expires_on))
        self._marked.add(key)


@pytest.mark.covers("B8.1")
def test_send_expiry_reminders_is_idempotent():
    """B8.1: первый запуск шлёт всем кандидатам, повторный — никому."""
    bot_id = 1
    days = 3
    now = datetime.now(timezone.utc)
    expires_on = (now + timedelta(days=days)).date()

    rows = [
        {"tg_user_id": 111, "plan_name": "TEST 4", "expires_at": now + timedelta(days=days)},
        {"tg_user_id": 222, "plan_name": "TEST 8", "expires_at": now + timedelta(days=days, hours=1)},
    ]
    pool = FakePool(rows)
    bot = FakeBotAPI()

    # Первый проход — шлём 2 уведомления
    sent1 = asyncio.run(send_expiry_reminders(pool=pool, bot_api=bot, bot_id=bot_id, days_ahead=days))
    assert sent1 == 2
    assert len(bot.sent) == 2
    # Текст содержит план и дату
    for _, text in bot.sent:
        assert "TEST" in text and str(expires_on) in text

    # Повторный проход — не шлём повторно
    sent2 = asyncio.run(send_expiry_reminders(pool=pool, bot_api=bot, bot_id=bot_id, days_ahead=days))
    assert sent2 == 0
    assert len(bot.sent) == 2  # без дубликатов
