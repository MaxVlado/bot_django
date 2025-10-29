"""
B7.2 — Один пользователь в двух ботах: независимые статусы и списки планов.

Ожидание:
- on_status: при BOT_ID=1 показывается статус/план бота 1; при BOT_ID=2 — только бота 2.
- on_renew: при BOT_ID=1 видны только планы бота 1; при BOT_ID=2 — только бота 2.
"""

import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.subscriptions import on_status, on_renew  # ✅ ИСПРАВЛЕНО: импорт из subscriptions


# ----- Фейки -----
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

    async def answer(self, *_, **__):
        self.answered = True


class FakePoolStatusByBot:
    """
    fetchval(...) -> False (не заблокирован)
    fetchrow(sql, bot_id, user_id) -> возвращает строку именно для bot_id
    """
    def __init__(self, row_by_bot):
        self.row_by_bot = dict(row_by_bot)

    async def fetchval(self, *_args, **_kwargs):
        return False

    async def fetchrow(self, _sql: str, bot_id: int, _user_id: int):
        return self.row_by_bot.get(bot_id)


class FakePoolPlansByBot:
    """
    fetchval(...) -> False
    fetch(sql, bot_id) -> возвращает список планов только для bot_id (enabled=True)
    """
    def __init__(self, plans):
        self.plans = list(plans)

    async def fetchval(self, *_args, **_kwargs):
        return False

    async def fetch(self, _sql: str, bot_id: int, *_args):
        return [p for p in self.plans if p.get("bot_id") == bot_id and p.get("enabled", True)]


# ✅ ДОБАВЛЕНО: Фейковый bot_model
class FakeBotModel:
    def __init__(self, bot_id: int):
        self.id = bot_id
        self.bot_id = bot_id
        self.title = f"Test Bot {bot_id}"
        self.username = f"test_bot_{bot_id}"
        self.token = f"TEST_TOKEN_{bot_id}"


# ----- Тесты -----
@pytest.mark.covers("B7.2")
def test_status_independent_per_bot():
    """B7.2: Статус подписки один и тот же user_id видит разный для разных BOT_ID."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    row_bot1 = ("active", now - timedelta(days=1), now + timedelta(days=29), now - timedelta(hours=12),
                "PLAN-ONE", 4, "UAH", 7)
    row_bot2 = ("expired", now - timedelta(days=40), now - timedelta(days=10), now - timedelta(days=40),
                "PLAN-TWO", 8, "UAH", 30)

    pool = FakePoolStatusByBot({1: row_bot1, 2: row_bot2})
    user_id = 100500

    # BOT_ID = 1
    # ✅ ИСПРАВЛЕНО: Создаём bot_model вместо мокирования BOT_ID
    bot_model_1 = FakeBotModel(bot_id=1)
    cb1 = FakeCallbackQuery(user_id, "sub:status")
    asyncio.run(on_status(cb1, pool, bot_model_1))
    txt1 = cb1.message.last_text or ""
    assert "PLAN-ONE" in txt1 and "4 UAH" in txt1
    assert cb1.answered is True

    # BOT_ID = 2
    # ✅ ИСПРАВЛЕНО: Создаём bot_model вместо мокирования BOT_ID
    bot_model_2 = FakeBotModel(bot_id=2)
    cb2 = FakeCallbackQuery(user_id, "sub:status")
    asyncio.run(on_status(cb2, pool, bot_model_2))
    txt2 = cb2.message.last_text or ""
    assert "PLAN-TWO" in txt2 and "8 UAH" in txt2
    assert "PLAN-ONE" not in txt2, "Данные другого бота не должны утекать"
    assert cb2.answered is True


@pytest.mark.covers("B7.2")
def test_plans_list_independent_per_bot():
    """B7.2: «Продлить подписку» показывает разные планы для разных BOT_ID."""
    plans = [
        {"id": 10, "bot_id": 1, "name": "B1-4", "price": 4, "currency": "UAH", "duration_days": 7, "enabled": True},
        {"id": 11, "bot_id": 1, "name": "B1-8", "price": 8, "currency": "UAH", "duration_days": 30, "enabled": True},
        {"id": 20, "bot_id": 2, "name": "B2-16", "price": 16, "currency": "UAH", "duration_days": 30, "enabled": True},
    ]
    pool = FakePoolPlansByBot(plans)
    user_id = 100500

    # BOT_ID = 1
    # ✅ ИСПРАВЛЕНО: Создаём bot_model вместо мокирования BOT_ID
    bot_model_1 = FakeBotModel(bot_id=1)
    cb1 = FakeCallbackQuery(user_id, "sub:renew")
    asyncio.run(on_renew(cb1, pool, bot_model_1))
    kb1 = cb1.message.last_markup
    btns1 = [b for row in kb1.inline_keyboard for b in row]
    calls1 = [getattr(b, "callback_data", "") for b in btns1]
    assert "pay:10" in calls1 and "pay:11" in calls1
    assert "pay:20" not in calls1
    assert cb1.answered is True

    # BOT_ID = 2
    # ✅ ИСПРАВЛЕНО: Создаём bot_model вместо мокирования BOT_ID
    bot_model_2 = FakeBotModel(bot_id=2)
    cb2 = FakeCallbackQuery(user_id, "sub:renew")
    asyncio.run(on_renew(cb2, pool, bot_model_2))
    kb2 = cb2.message.last_markup
    btns2 = [b for row in kb2.inline_keyboard for b in row]
    calls2 = [getattr(b, "callback_data", "") for b in btns2]
    assert "pay:20" in calls2
    assert "pay:10" not in calls2 and "pay:11" not in calls2
    assert cb2.answered is True