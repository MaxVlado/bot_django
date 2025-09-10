"""
B6.2 — Одновременно APPROVED и затем DECLINED по тому же orderReference:
уведомление об успехе не отзывается. Допустимо отправить информативное сообщение о неуспехе.
"""

import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.main import notify_payment_success, notify_payment_non_success  # noqa: E402


class FakeBotAPI:
    """Мок Telegram Bot API (совместим по send_message)."""
    def __init__(self):
        self.sent = []  # список (chat_id, text, parse_mode)

    async def send_message(self, chat_id: int, text: str, parse_mode: str | None = None, **kwargs):
        self.sent.append((chat_id, text, parse_mode))


class FakePool:
    """
    Простое «хранилище» идемпотентности:
      - fetchval(sql, order_reference) -> True/False
      - execute(sql, order_reference)  -> помечает как отправленное
    """
    def __init__(self):
        self._marked = set()

    async def fetchval(self, *_args, **kwargs):
        order_ref = kwargs.get("order_reference")
        if order_ref is None and _args:
            order_ref = _args[-1]
        return str(order_ref) in self._marked

    async def execute(self, *_args, **kwargs):
        order_ref = kwargs.get("order_reference")
        if order_ref is None and _args:
            order_ref = _args[-1]
        if order_ref is not None:
            self._marked.add(str(order_ref))


@pytest.mark.covers("B6.2")
def test_non_success_after_success_does_not_revoke_success():
    """B6.2: после отправки 'успеха' последующий DECLINED не «откатывает» уведомление."""
    bot = FakeBotAPI()
    pool = FakePool()

    user_id = 123456
    order_ref = "OR-MIXED-777"

    # 1) Пришёл APPROVED — отправляем подтверждение
    sent_now = asyncio.run(
        notify_payment_success(
            pool=pool,
            bot_api=bot,
            user_id=user_id,
            order_reference=order_ref,
            plan_name="TEST 8",
            expires_at=None,
        )
    )
    assert sent_now is True
    assert len(bot.sent) == 1
    assert "Платёж подтверждён" in bot.sent[0][1]

    # 2) Затем пришёл DECLINED по тому же orderReference — можно информировать, но НЕ отменять успех
    asyncio.run(
        notify_payment_non_success(
            bot_api=bot,
            user_id=user_id,
            order_reference=order_ref,
            status="DECLINED",
            reason="bank-decline",
        )
    )

    assert len(bot.sent) == 2, "Ожидалось одно информативное сообщение после успеха"
    # Второе сообщение не должно содержать текста про подтверждение
    assert "Платёж подтверждён" not in bot.sent[1][1]
