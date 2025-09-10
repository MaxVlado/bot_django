"""
B2.3 — Наличие нескольких подписок в истории: отображается актуальная (по updated_at).

Ожидание:
- on_status использует выборку с ORDER BY s.updated_at DESC LIMIT 1.
- В карточке статуса отображаются данные «последней» подписки (по updated_at).
- parse_mode="HTML", есть inline-клавиатура, колбэк подтверждён.
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
    - fetchval(...) -> is_blocked=False
    - fetchrow(sql, bot_id, user_id) -> возвращает 'последнюю' строку, если SQL содержит нужный ORDER BY.
    """
    def __init__(self, latest_row, old_row):
        self.latest_row = latest_row
        self.old_row = old_row

    async def fetchval(self, *_args, **_kwargs):
        return False  # не заблокирован

    async def fetchrow(self, sql: str, *_args, **_kwargs):
        # Проверяем, что обработчик действительно использует нужный ORDER BY
        if "ORDER BY s.updated_at DESC" in sql and "LIMIT 1" in sql:
            return self.latest_row
        # Если вдруг забудут сортировку — вернётся «старая» строка, и тест упадёт
        return self.old_row


@pytest.mark.covers("B2.3")
def test_status_shows_latest_subscription():
    """B2.3: Должна отображаться актуальная подписка (по updated_at DESC)."""
    now = datetime.now(timezone.utc)

    old = (
        "active",                 # status
        now - timedelta(days=60), # starts_at
        now - timedelta(days=30), # expires_at (уже истёкшая)
        now - timedelta(days=60), # last_payment_date
        "OLD 4",                  # plan name
        4,                        # price
        "UAH",                    # currency
        7,                        # duration_days
    )

    latest = (
        "active",
        now - timedelta(days=2),
        now + timedelta(days=28),
        now - timedelta(days=1),
        "LATEST 8",
        8,
        "UAH",
        30,
    )

    cb = FakeCallbackQuery(user_id=123456)
    pool = FakePool(latest_row=latest, old_row=old)

    asyncio.run(on_status(cb, pool))

    txt = cb.message.last_text or ""
    # В карточке должен быть «latest» план
    assert "LATEST 8" in txt, "Ожидалась актуальная подписка по updated_at DESC"
    assert "8 UAH" in txt

    # parse_mode и клавиатура присутствуют
    assert cb.message.last_parse_mode == "HTML"
    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard") and len(kb.inline_keyboard) >= 1

    # Колбэк подтверждён
    assert cb.answered is True
