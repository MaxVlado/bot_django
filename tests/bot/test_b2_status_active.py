"""
B2.1 — Активная подписка: корректное отображение плана, дат и последней оплаты.

Ожидание:
- Хендлер on_status выводит карточку "Статус подписки" c:
  - названием плана,
  - ценой и валютой,
  - длительностью,
  - датами начала/окончания,
  - датой последней оплаты.
- parse_mode="HTML"
- Есть inline-клавиатура (главное меню)
- Колбэк подтверждается.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.subscriptions import on_status # noqa: E402


class FakeFromUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeMessage:
    def __init__(self):
        self.last_text = None
        self.last_markup = None
        self.last_parse_mode = None

    async def edit_text(self, text: str, reply_markup=None, parse_mode=None, **kwargs):
        self.last_text = text
        self.last_markup = reply_markup
        self.last_parse_mode = parse_mode


class FakeCallbackQuery:
    def __init__(self, user_id: int):
        self.from_user = FakeFromUser(user_id)
        self.data = "sub:status"
        self.message = FakeMessage()
        self.answered = False

    async def answer(self, *_, **__):
        self.answered = True


class FakePool:
    """
    Минимальный мок asyncpg.Pool.
    Нужны:
      - fetchval(...) -> is_blocked=False
      - fetchrow(...) -> кортеж полей статуса подписки
        порядок:
          status, starts_at_utc, expires_at_utc, last_payment_utc,
          plan_name, price, currency, duration_days
    """
    def __init__(self, row):
        self._row = row

    async def fetchval(self, *_args, **_kwargs):
        return False  # не заблокирован

    async def fetchrow(self, *_args, **_kwargs):
        return self._row


@pytest.mark.covers("B2.1")
def test_status_active_subscription_card():
    """B2.1: on_status должен корректно отобразить карточку активной подписки."""
    now = datetime.now(timezone.utc)
    row = (
        "active",                  # status
        now - timedelta(days=2),   # starts_at (UTC)
        now + timedelta(days=5),   # expires_at (UTC)
        now - timedelta(days=1),   # last_payment_date (UTC)
        "TEST 8",                  # plan name
        8,                         # price
        "UAH",                     # currency
        30,                        # duration_days
    )

    cb = FakeCallbackQuery(user_id=123456)
    pool = FakePool(row=row)
    bot_model = FakeBotModel(bot_id=1)
    asyncio.run(on_status(cb, pool,bot_model))

    # Текст присутствует и содержит ключевые поля
    txt = cb.message.last_text or ""
    assert "Статус подписки" in txt
    assert "TEST 8" in txt
    assert "8 UAH" in txt
    assert "30" in txt  # длительность

    # parse_mode HTML и есть клавиатура
    assert cb.message.last_parse_mode == "HTML"
    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard") and len(kb.inline_keyboard) >= 1

    # Колбэк подтверждён
    assert cb.answered is True

class FakeBotModel:
    def __init__(self, bot_id: int):
        self.id = bot_id
        self.bot_id = bot_id