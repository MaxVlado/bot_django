"""
B9.1 — Сетевой сбой при обращении к Django API (соединение/DNS/timeout).

Ожидание:
- on_pay ловит исключение сети и показывает alert с текстом ошибки.
- Сообщение НЕ редактируется (кнопка оплаты не появляется).
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


class FakeSessionRaises:
    """Имитирует сетевую ошибку при POST (например, DNS/timeout)."""
    def post(self, *_args, **_kwargs):
        raise OSError("network unreachable")


@pytest.mark.covers("B9.1")
def test_on_pay_network_error_shows_alert(monkeypatch):
    """B9.1: сетевое исключение → alert 'Ошибка ...', без кнопки оплаты."""
    cb = FakeCallbackQuery(user_id=123456, plan_id=42)
    session = FakeSessionRaises()

    asyncio.run(on_pay(cb, session))

    # Колбэк подтверждён и это alert
    assert cb.answered is True
    assert cb.last_show_alert is True
    assert cb.last_answer_text and "Ошибка" in cb.last_answer_text

    # Сообщение не редактировалось (кнопка оплаты не появилась)
    assert cb.message.last_markup is None
