"""
B3.3 — План выключен (enabled=False): тариф не отображается в списке продления.
"""
import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.subscriptions import on_renew  # ✅ ИЗМЕНЕНО


class FakeFromUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeMessage:
    def __init__(self):
        self.last_text = None
        self.last_markup = None

    async def edit_text(self, text: str, reply_markup=None, **kwargs):
        self.last_text = text
        self.last_markup = reply_markup


class FakeCallbackQuery:
    def __init__(self, user_id: int):
        self.from_user = FakeFromUser(user_id)
        self.data = "sub:renew"
        self.message = FakeMessage()
        self.answered = False

    async def answer(self, *_, **__):
        self.answered = True


class FakePool:
    def __init__(self, plans):
        self._plans = plans

    async def fetchval(self, *_args, **_kwargs):
        return False

    async def fetch(self, *_args, **_kwargs):
        return self._plans


# ✅ ДОБАВЛЕНО
class FakeBotModel:
    def __init__(self, bot_id: int):
        self.id = bot_id
        self.bot_id = bot_id


@pytest.mark.covers("B3.3")
def test_renew_hides_disabled_plans():
    """B3.3: Выключенный план не должен попадать в клавиатуру оплаты."""
    cb = FakeCallbackQuery(user_id=123456)
    plans = [
        {"id": 10, "name": "TEST 4", "price": 4, "currency": "UAH", "duration_days": 7, "enabled": True},
        {"id": 99, "name": "OLD 99", "price": 99, "currency": "UAH", "duration_days": 1, "enabled": False},
        {"id": 11, "name": "TEST 8", "price": 8, "currency": "UAH", "duration_days": 30, "enabled": True},
    ]
    pool = FakePool(plans=plans)
    bot_model = FakeBotModel(bot_id=1)  # ✅ ДОБАВЛЕНО

    asyncio.run(on_renew(cb, pool, bot_model))  # ✅ ИЗМЕНЕНО

    assert cb.message.last_text and "Выберите тариф" in cb.message.last_text

    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard")
    buttons = [b for row in kb.inline_keyboard for b in row]

    pay_callbacks = [getattr(b, "callback_data", "") for b in buttons if getattr(b, "callback_data", "").startswith("pay:")]
    assert "pay:10" in pay_callbacks
    assert "pay:11" in pay_callbacks
    assert "pay:99" not in pay_callbacks

    assert any(cbdata == "ui:back" or getattr(b, "text", "") == "⬅ Назад" for b in buttons
               for cbdata in [getattr(b, "callback_data", "")])
    assert cb.answered is True