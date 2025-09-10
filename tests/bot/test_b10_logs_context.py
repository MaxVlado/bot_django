"""
B10.2 — Ошибки API/DB содержат достаточный контекст (bot_id, user_id, plan_id, orderReference).

Ожидание:
- При сетевой ошибке в on_pay лог содержит bot_id, user_id, plan_id.
- orderReference для create-invoice ещё неизвестен — поэтому не требуем его здесь.
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

    async def answer(self, text: str | None = None, show_alert: bool | None = None, **_):
        self.answered = True
        self.last_answer_text = text
        self.last_show_alert = show_alert


class FakeSessionRaises:
    """Имитирует сетевую ошибку при POST (например, DNS/timeout)."""
    def post(self, *_args, **_kwargs):
        raise OSError("network unreachable")


@pytest.mark.covers("B10.2")
def test_on_pay_logs_context_on_error(monkeypatch, caplog):
    """B10.2: лог on_pay при ошибке должен включать bot_id, user_id, plan_id."""
    # фиксируем BOT_ID
    monkeypatch.setattr(botmod, "BOT_ID", 1)

    cb = FakeCallbackQuery(user_id=123456, plan_id=42)
    session = FakeSessionRaises()

    with caplog.at_level("ERROR", logger="bot"):
        asyncio.run(on_pay(cb, session))

    # Ищем запись нашего логгера
    msgs = [rec.getMessage() for rec in caplog.records if rec.name == "bot"]
    assert msgs, "Ожидалась хотя бы одна запись логов от логгера 'bot'"

    # Сообщение должно содержать контекст
    joint = "\n".join(msgs)
    assert "bot_id=1" in joint
    assert "user_id=123456" in joint
    assert "plan_id=42" in joint
