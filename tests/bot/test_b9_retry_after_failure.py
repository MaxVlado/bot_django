"""
B9.2 — Повтор запроса create-invoice после временного сбоя: успешное получение URL.

Ожидание:
- Первый вызов on_pay падает с сетевой ошибкой → показываем alert, кнопка оплаты НЕ появляется.
- Пользователь повторяет действие (второй вызов on_pay) → успешный ответ API, появляется кнопка «Оплатить».
"""

import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
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
        self.last_answer_text = None
        self.last_show_alert = None

    async def answer(self, text: str | None = None, show_alert: bool | None = None, **_):
        self.answered = True
        self.last_answer_text = text
        self.last_show_alert = show_alert


class FakeResp:
    def __init__(self, json_data):
        self._json = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json


class FakeSessionFlaky:
    """
    Первый post(...) — кидает OSError (временный сетевой сбой),
    последующие — возвращают ok=True с invoiceUrl.
    """
    def __init__(self):
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary network failure")
        return FakeResp({"ok": True, "invoiceUrl": "https://secure.wayforpay.com/pay?retry=1"})


@pytest.mark.covers("B9.2")
def test_retry_after_temporary_failure_succeeds():
    """B9.2: после временного сбоя повторный вызов даёт кнопку «Оплатить»."""
    session = FakeSessionFlaky()

    # 1) Первый вызов — ошибка сети → alert, без кнопки оплаты
    cb1 = FakeCallbackQuery(user_id=123456, plan_id=7)
    asyncio.run(on_pay(cb1, session))
    assert cb1.answered is True
    assert cb1.last_show_alert is True
    assert cb1.last_answer_text and "Ошибка" in cb1.last_answer_text
    assert cb1.message.last_markup is None, "Кнопка оплаты не должна появиться при ошибке сети"

    # 2) Пользователь повторяет действие → успешный ответ API, появляется кнопка «Оплатить»
    cb2 = FakeCallbackQuery(user_id=123456, plan_id=7)
    asyncio.run(on_pay(cb2, session))

    kb = cb2.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard")
    # ищем кнопку с URL WayForPay
    buttons = [b for row in kb.inline_keyboard for b in row]
    pay_buttons = [b for b in buttons if (getattr(b, "url", "") or "").startswith("https://secure.wayforpay.com/pay")]
    assert len(pay_buttons) == 1, "Должна появиться кнопка «Оплатить» после успешного повтора"
