"""
B2.2 — Просроченная подписка: статус expired, предложение продлить.

Ожидание:
- Хендлер on_status выводит карточку "Статус подписки" со статусом expired.
- Печатает базовые поля (план, цена/валюта, длительность, даты).
- В тексте есть подсказка о продлении.
- parse_mode="HTML", есть inline-клавиатура (главное меню), колбэк подтверждён.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.main import on_status  # noqa: E402


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
      - fetchrow(...) -> кортеж полей:
        status, starts_at_utc, expires_at_utc, last_payment_utc,
        plan_name, price, currency, duration_days
    """
    def __init__(self, row):
        self._row = row

    async def fetchval(self, *_args, **_kwargs):
        return False  # не заблокирован

    async def fetchrow(self, *_args, **_kwargs):
        return self._row


@pytest.mark.covers("B2.2")
def test_status_expired_subscription_shows_renew_hint():
    """B2.2: on_status должен показать статус 'expired' и подсказать про продление."""
    now = datetime.now(timezone.utc)
    row = (
        "expired",                 # status
        now - timedelta(days=40),  # starts_at
        now - timedelta(days=10),  # expires_at (в прошлом)
        now - timedelta(days=40),  # last_payment_date
        "TEST 4",                  # plan name
        4,                         # price
        "UAH",                     # currency
        7,                         # duration_days
    )

    cb = FakeCallbackQuery(user_id=123456)
    pool = FakePool(row=row)

    asyncio.run(on_status(cb, pool))

    txt = cb.message.last_text or ""
    # Карточка и статус
    assert "Статус подписки" in txt
    assert "expired" in txt.lower()
    # Базовые поля
    assert "TEST 4" in txt and "4 UAH" in txt and "7" in txt
    # Подсказка о продлении (формулировка из bot.main)
    assert "Продлить" in txt or "продления" in txt or "Для продления" in txt

    # parse_mode и клавиатура
    assert cb.message.last_parse_mode == "HTML"
    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard") and len(kb.inline_keyboard) >= 1

    # Колбэк подтверждён
    assert cb.answered is True
