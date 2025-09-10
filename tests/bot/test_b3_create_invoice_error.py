"""
B3.2 — Ошибка при создании инвойса: корректное сообщение пользователю (alert).

Ожидание:
- Если Django API вернул {"ok": false, "error": "..."} — бот показывает alert с текстом ошибки.
- Если при POST случилось сетевое/иное исключение — бот показывает alert "Ошибка запроса".
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
        self.last_answer_text = None
        self.last_show_alert = None

    async def answer(self, text: str | None = None, show_alert: bool | None = None, *_, **__):
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


class FakeSessionOKFalse:
    """Имитирует HTTP 200 с ok=false и сообщением об ошибке."""
    def __init__(self):
        self.last_url = None
        self.last_json = None
        self.timeout = None

    def post(self, url, json, timeout):
        self.last_url = url
        self.last_json = json
        self.timeout = timeout
        return FakeResp({"ok": False, "error": "bad things happened"})


class FakeSessionRaises:
    """Имитирует сетевую/внутреннюю ошибку при POST."""
    def post(self, *_args, **_kwargs):
        raise RuntimeError("network down")


@pytest.mark.covers("B3.2")
def test_on_pay_api_returns_error_alerts_user(monkeypatch):
    """B3.2: ok=false от API — должен быть alert с текстом ошибки."""
    monkeypatch.setattr(botmod, "BOT_ID", 1)
    monkeypatch.setattr(botmod, "API_BASE", "http://127.0.0.1:8000/api/payments/wayforpay")

    cb = FakeCallbackQuery(user_id=123, plan_id=7)
    session = FakeSessionOKFalse()

    asyncio.run(on_pay(cb, session))

    assert cb.answered is True
    assert cb.last_show_alert is True
    assert cb.last_answer_text and "Ошибка" in cb.last_answer_text


@pytest.mark.covers("B3.2")
def test_on_pay_network_exception_alerts_user(monkeypatch):
    """B3.2: исключение при POST — должен быть alert 'Ошибка запроса'."""
    monkeypatch.setattr(botmod, "BOT_ID", 1)
    monkeypatch.setattr(botmod, "API_BASE", "http://127.0.0.1:8000/api/payments/wayforpay")

    cb = FakeCallbackQuery(user_id=456, plan_id=42)
    session = FakeSessionRaises()

    asyncio.run(on_pay(cb, session))

    assert cb.answered is True
    assert cb.last_show_alert is True
    assert cb.last_answer_text and "Ошибка" in cb.last_answer_text
