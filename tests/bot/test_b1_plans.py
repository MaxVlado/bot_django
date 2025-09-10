"""
B1.3 — «Продлить подписку»: показ списка активных тарифов по текущему BOT_ID.

Ожидание:
- Хендлер on_renew рендерит текст "Выберите тариф для продления:"
- В inline-клавиатуре есть кнопки по числу планов + кнопка «Назад»
- Кнопки оплаты имеют callback_data вида "pay:<plan_id>"
"""
import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.main import on_renew  # noqa: E402


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
    """
    Минимальный мок asyncpg.Pool.
    Нужно:
      - fetchval(...) -> is_blocked=False
      - fetch(...) -> список планов (id, name, price, currency, duration_days)
    """
    def __init__(self, blocked: bool = False, plans=None):
        self._blocked = blocked
        self._plans = plans or []

    async def fetchval(self, *_args, **_kwargs):
        return self._blocked

    async def fetch(self, *_args, **_kwargs):
        # Возвращаем список dict-подобных записей
        return self._plans


@pytest.mark.covers("B1.3")
def test_renew_shows_available_plans_list():
    """B1.3: «Продлить подписку» должно показать список активных тарифов и кнопки оплаты."""
    cb = FakeCallbackQuery(user_id=123456)
    # Два тестовых плана
    plans = [
        {"id": 10, "name": "TEST 4", "price": 4, "currency": "UAH", "duration_days": 7},
        {"id": 11, "name": "TEST 8", "price": 8, "currency": "UAH", "duration_days": 30},
    ]
    pool = FakePool(blocked=False, plans=plans)

    asyncio.run(on_renew(cb, pool))

    # Текст-заголовок
    assert cb.message.last_text is not None
    assert "Выберите тариф для продления" in cb.message.last_text

    # Клавиатура: 2 кнопки планов + 1 кнопка "Назад"
    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard")
    # плоский список всех кнопок
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    # найдём кнопки с pay:<id>
    pay_buttons = [b for b in all_buttons if getattr(b, "callback_data", "").startswith("pay:")]
    assert len(pay_buttons) == len(plans)
    assert any(getattr(b, "callback_data", "") == "ui:back" for b in all_buttons) or \
           any(getattr(b, "text", "") == "⬅ Назад" for b in all_buttons)

    # Содержимое кнопок корректно отображает цену/срок
    texts = [getattr(b, "text", "") for b in pay_buttons]
    assert any("4 UAH" in t and "7" in t for t in texts)
    assert any("8 UAH" in t and "30" in t for t in texts)

    # Колбэк подтверждён
    assert cb.answered is True
