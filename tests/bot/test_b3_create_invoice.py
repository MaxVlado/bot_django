"""
B3.1 — Выбор тарифа → POST /create-invoice → получен invoiceUrl.

Ожидание:
- Хендлер on_pay делает POST на API_BASE/create-invoice/ c payload {bot_id, user_id, plan_id}.
- При успешном ответе ok + invoiceUrl — бот редактирует сообщение, показывая кнопку «💳 Оплатить» с правильным URL.
- Есть кнопка «⬅ Назад».
- Колбэк подтверждается (cb.answer()).
"""
import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
import bot.main as botmod  # noqa: E402
from bot.main import on_pay  # noqa: E402


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
    def __init__(self, user_id: int, plan_id: int):
        self.from_user = FakeFromUser(user_id)
        self.data = f"pay:{plan_id}"
        self.message = FakeMessage()
        self.answered = False

    async def answer(self, *_, **__):
        self.answered = True


class FakeResp:
    def __init__(self, json_data):
        self._json = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json


class FakeSession:
    def __init__(self):
        self.last_url = None
        self.last_json = None
        self.timeout = None

    def post(self, url, json, timeout):
        self.last_url = url
        self.last_json = json
        self.timeout = timeout
        # Успешный ответ Django API
        return FakeResp({"ok": True, "invoiceUrl": "https://secure.wayforpay.com/pay?test=1"})


@pytest.mark.covers("B3.1")
def test_on_pay_success_shows_invoice_button(monkeypatch):
    """B3.1: on_pay должен отправить POST и показать кнопку оплаты с корректным URL."""
    # фиксируем окружение бота
    monkeypatch.setattr(botmod, "BOT_ID", 1)
    monkeypatch.setattr(botmod, "API_BASE", "http://127.0.0.1:8000/api/payments/wayforpay")

    cb = FakeCallbackQuery(user_id=123456, plan_id=42)
    session = FakeSession()

    asyncio.run(on_pay(cb, session))

    # Проверяем, что был POST на правильный URL и с нужным payload
    assert session.last_url.endswith("/create-invoice/")
    assert session.last_json == {"bot_id": 1, "user_id": 123456, "plan_id": 42}

    # Сообщение отредактировано и есть кнопка с invoiceUrl
    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard")
    # плоский список всех кнопок
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    # url может быть None, поэтому (.. or "")
    pay_buttons = [b for b in buttons if (getattr(b, "url", "") or "").startswith("https://secure.wayforpay.com/pay")]
    assert len(pay_buttons) == 1, "Должна быть одна кнопка «Оплатить» с URL WayForPay"

    # Есть кнопка «Назад»
    assert any(
        getattr(b, "callback_data", "") == "ui:back" or getattr(b, "text", "") == "⬅ Назад"
        for b in buttons
    ), "Должна быть кнопка «⬅ Назад»"

    # Колбэк подтверждён
    assert cb.answered is True
