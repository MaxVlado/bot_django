"""
B4.2 — Повторный APPROVED того же orderReference в рамках одной сессии:
бот НЕ должен слать дубликат подтверждения.
"""

import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.main import notify_payment_success  # noqa: E402


class FakeBotAPI:
    """Мок Telegram Bot API (совместим по send_message)."""
    def __init__(self):
        self.sent = []  # список (chat_id, text, parse_mode)

    async def send_message(self, chat_id: int, text: str, parse_mode: str | None = None, **kwargs):
        self.sent.append((chat_id, text, parse_mode))


class FakePool:
    """
    Минимальный мок «идемпотентного» хранилища отправок:
      - fetchval(sql, order_reference) -> True/False
      - execute(sql, order_reference)  -> помечает как отправленное
    """
    def __init__(self):
        self._notified = set()

    async def fetchval(self, *_args, **kwargs):
        order_ref = kwargs.get("order_reference")
        if order_ref is None and _args:
            order_ref = _args[-1]
        return str(order_ref) in self._notified

    async def execute(self, *_args, **kwargs):
        order_ref = kwargs.get("order_reference")
        if order_ref is None and _args:
            order_ref = _args[-1]
        if order_ref is not None:
            self._notified.add(str(order_ref))


@pytest.mark.covers("B4.2")
def test_duplicate_approved_in_same_session_is_suppressed():
    """B4.2: второй вызов notify_payment_success с тем же orderReference не шлёт дубль."""
    bot = FakeBotAPI()
    pool = FakePool()

    user_id = 777001
    order_ref = "OR-DUP-42"
    plan_name = "TEST 8"

    # первый вызов — сообщение должно уйти
    asyncio.run(notify_payment_success(pool=pool, bot_api=bot, user_id=user_id,
                                       order_reference=order_ref, plan_name=plan_name, expires_at=None))
    assert len(bot.sent) == 1

    # повторный вызов в той же сессии — не должно уйти второе
    asyncio.run(notify_payment_success(pool=pool, bot_api=bot, user_id=user_id,
                                       order_reference=order_ref, plan_name=plan_name, expires_at=None))
    assert len(bot.sent) == 1, "Дубликат подтверждения не должен отправляться"
