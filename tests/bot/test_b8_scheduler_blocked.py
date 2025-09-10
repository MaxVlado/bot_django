"""
B8.2 — Планировщик не шлёт DM заблокированным пользователям.

Ожидание:
- send_expiry_reminders пропускает tg_user_id, для которых is_blocked=True.
- Отправляет только незаблокированным.
- Идемпотентность сохраняется: повторный запуск не шлёт дубликаты.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.scheduler import send_expiry_reminders  # noqa: E402


class FakeBotAPI:
    def __init__(self):
        self.sent = []  # (chat_id, text)

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.sent.append((chat_id, text))


class FakePool:
    """
    Мок asyncpg.Pool для напоминаний с поддержкой блокировки.
    Поддерживает:
      - fetch(...) -> список кандидатов
      - fetchval(SQL_REMINDER_ALREADY_SENT, bot_id, tg_user_id, expires_on) -> bool
      - fetchval(SQL_IS_BLOCKED, tg_user_id) -> bool
      - execute(...) -> пометить как отправленное
    """
    def __init__(self, rows, blocked_ids: set[int]):
        self._rows = list(rows)
        self._blocked = set(blocked_ids)
        self._marked = set()  # (bot_id, tg_user_id, expires_on)

    async def fetch(self, *_args, **_kwargs):
        return self._rows

    async def fetchval(self, *args, **kwargs):
        # Разрулим по количеству позиционных аргументов:
        #  - (sql, bot_id, tg_user_id, expires_on) -> проверка идемпотентности
        #  - (sql, tg_user_id) -> проверка блокировки
        if len(args) >= 4:
            _, bot_id, tg_user_id, expires_on = args[:4]
            key = (int(bot_id), int(tg_user_id), str(expires_on))
            return key in self._marked
        elif len(args) >= 2:
            _, tg_user_id = args[:2]
            return int(tg_user_id) in self._blocked
        else:
            raise AssertionError("Unexpected fetchval signature in FakePool")

    async def execute(self, *args, **kwargs):
        # (sql, bot_id, tg_user_id, expires_on)
        _, bot_id, tg_user_id, expires_on = args[:4]
        key = (int(bot_id), int(tg_user_id), str(expires_on))
        self._marked.add(key)


@pytest.mark.covers("B8.2")
def test_scheduler_skips_blocked_users():
    """B8.2: заблокированным не шлём, незаблокированным — шлём один раз."""
    bot_id = 1
    days = 3
    now = datetime.now(timezone.utc)
    exp_date = now + timedelta(days=days)

    rows = [
        {"tg_user_id": 111, "plan_name": "TEST 4", "expires_at": exp_date},  # заблокирован
        {"tg_user_id": 222, "plan_name": "TEST 8", "expires_at": exp_date + timedelta(hours=1)}  # ок
    ]

    pool = FakePool(rows=rows, blocked_ids={111})
    bot = FakeBotAPI()

    # Первый прогон — должно уйти только 1 сообщение (для 222)
    sent1 = asyncio.run(send_expiry_reminders(pool=pool, bot_api=bot, bot_id=bot_id, days_ahead=days))
    assert sent1 == 1
    assert len(bot.sent) == 1 and bot.sent[0][0] == 222

    # Повторный прогон — дубликатов нет
    sent2 = asyncio.run(send_expiry_reminders(pool=pool, bot_api=bot, bot_id=bot_id, days_ahead=days))
    assert sent2 == 0
    assert len(bot.sent) == 1
