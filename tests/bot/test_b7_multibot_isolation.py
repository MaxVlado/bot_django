"""
B7.1 — Планы и статусы отображаются строго для текущего BOT_ID (изоляция многоботности).
"""

import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
import bot.main as botmod  # noqa: E402
from bot.main import on_renew, on_status  # noqa: E402


# ---------- Фейки для on_renew ----------
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
    def __init__(self, user_id: int, data: str):
        self.from_user = FakeFromUser(user_id)
        self.data = data
        self.message = FakeMessage()
        self.answered = False
        self.last_answer_text = None
        self.last_show_alert = None

    async def answer(self, text: str | None = None, show_alert: bool | None = None, **_):
        self.answered = True
        self.last_answer_text = text
        self.last_show_alert = show_alert


# ---------- Пулы c фильтрацией по bot_id ----------
class FakePoolPlans:
    """
    Мок asyncpg.Pool для on_renew:
      - fetchval(...) -> is_blocked=False
      - fetch(sql, bot_id) -> вернёт только планы, где rec["bot_id"] == bot_id и enabled=True
    """
    def __init__(self, plans):
        self._plans = list(plans)

    async def fetchval(self, *_args, **_kwargs):
        return False

    async def fetch(self, _sql: str, bot_id: int, *_args):
        return [p for p in self._plans if p.get("bot_id") == bot_id and p.get("enabled", True)]


class FakePoolStatus:
    """
    Мок asyncpg.Pool для on_status:
      - fetchval(...) -> is_blocked=False
      - fetchrow(sql, bot_id, user_id) -> вернёт строку статуса, привязанную к bot_id
    """
    def __init__(self, rows_by_bot_id):
        self.rows_by_bot_id = dict(rows_by_bot_id)

    async def fetchval(self, *_args, **_kwargs):
        return False

    async def fetchrow(self, _sql: str, bot_id: int, _user_id: int):
        return self.rows_by_bot_id.get(bot_id)


@pytest.mark.covers("B7.1")
def test_on_renew_shows_only_current_bot_plans(monkeypatch):
    """B7.1: «Продлить подписку» должен показывать только планы текущего BOT_ID."""
    # Установим BOT_ID=1 для теста
    monkeypatch.setattr(botmod, "BOT_ID", 1)

    # Планы для разных ботов
    plans = [
        {"id": 10, "bot_id": 1, "name": "P-1/4", "price": 4, "currency": "UAH", "duration_days": 7, "enabled": True},
        {"id": 20, "bot_id": 2, "name": "P-2/99", "price": 99, "currency": "UAH", "duration_days": 1, "enabled": True},
        {"id": 11, "bot_id": 1, "name": "P-1/8", "price": 8, "currency": "UAH", "duration_days": 30, "enabled": True},
    ]
    pool = FakePoolPlans(plans)
    cb = FakeCallbackQuery(user_id=123456, data="sub:renew")

    asyncio.run(on_renew(cb, pool))

    # Собираем callback_data всех кнопок
    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard")
    all_buttons = [b for row in kb.inline_keyboard for b in row]
    pay_callbacks = [getattr(b, "callback_data", "") for b in all_buttons if getattr(b, "callback_data", "").startswith("pay:")]

    # Должны быть только планы BOT_ID=1
    assert "pay:10" in pay_callbacks
    assert "pay:11" in pay_callbacks
    assert "pay:20" not in pay_callbacks, "Планы другого бота не должны отображаться"


@pytest.mark.covers("B7.1")
def test_on_status_uses_current_bot_id(monkeypatch):
    """B7.1: Статус подписки должен браться для текущего BOT_ID (без утечки другого бота)."""
    monkeypatch.setattr(botmod, "BOT_ID", 1)

    # две "подписки" для разных ботов — проверим, что возьмётся именно bot_id=1
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    row_bot1 = (
        "active", now - timedelta(days=1), now + timedelta(days=29), now - timedelta(hours=12),
        "PLAN-ONE", 4, "UAH", 7
    )
    row_bot2 = (
        "active", now - timedelta(days=10), now + timedelta(days=20), now - timedelta(days=5),
        "PLAN-TWO", 99, "UAH", 1
    )

    pool = FakePoolStatus({1: row_bot1, 2: row_bot2})
    cb = FakeCallbackQuery(user_id=555777, data="sub:status")

    asyncio.run(on_status(cb, pool))

    txt = cb.message.last_text or ""
    assert "PLAN-ONE" in txt, "Ожидался план текущего бота"
    assert "PLAN-TWO" not in txt, "План другого бота не должен утекать в выдачу"
