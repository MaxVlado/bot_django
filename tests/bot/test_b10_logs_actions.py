"""
B10.1 — Действия бота логируются (start, статус, оплата).

Ожидание:
- При /start пишется INFO-лог с event=start и user_id.
- При status пишется INFO-лог с event=status, bot_id и user_id.
- При успешном create-invoice пишется INFO-лог с event=create_invoice_success и контекстом.
"""

import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
import bot.main as botmod  # noqa: E402
from bot.main import cmd_start, on_status, on_pay  # noqa: E402


# ---------- Фейки ----------
class FakeFromUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeMessage:
    def __init__(self, user_id: int):
        self.from_user = FakeFromUser(user_id)
        self.last_text = None
        self.last_markup = None

    async def answer(self, text: str, reply_markup=None, **kwargs):
        self.last_text = text
        self.last_markup = reply_markup


class FakeMsgForEdit:
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
        self.message = FakeMsgForEdit()
        self.answered = False
        self.last_answer_text = None
        self.last_show_alert = None

    async def answer(self, text: str | None = None, show_alert: bool | None = None, **_):
        self.answered = True
        self.last_answer_text = text
        self.last_show_alert = show_alert


class FakePoolStatusOK:
    """Пул для on_status: is_blocked=False и есть активная подписка."""
    def __init__(self, row):
        self._row = row

    async def fetchval(self, *_args, **_kwargs):
        return False  # не заблокирован

    async def fetchrow(self, *_args, **_kwargs):
        return self._row


class FakePoolUnblocked:
    async def fetchval(self, *_args, **_kwargs):
        return False  # для /start


class FakeResp:
    def __init__(self, json_data):
        self._json = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json


class FakeSessionOK:
    """Успешный ответ Django API на create-invoice."""
    def __init__(self):
        self.last_url = None
        self.last_json = None
        self.timeout = None

    def post(self, url, json, timeout):
        self.last_url = url
        self.last_json = json
        self.timeout = timeout
        return FakeResp({"ok": True, "invoiceUrl": "https://secure.wayforpay.com/pay?ok=1"})


# ---------- Тест ----------
@pytest.mark.covers("B10.1")
def test_actions_write_info_logs(monkeypatch, caplog):
    """B10.1: /start, status, успешный create-invoice должны писать INFO-логи с контекстом."""
    monkeypatch.setattr(botmod, "BOT_ID", 1)

    # 1) /start
    with caplog.at_level("INFO", logger="bot"):
        asyncio.run(cmd_start(FakeMessage(user_id=123), FakePoolUnblocked()))
    logs1 = [rec.getMessage() for rec in caplog.records if rec.name == "bot"]
    assert any("event=start" in m and "user_id=123" in m for m in logs1), "Ожидался лог event=start с user_id"

    caplog.clear()

    # 2) status (активная подписка)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    row = (
        "active", now - timedelta(days=1), now + timedelta(days=29), now - timedelta(hours=12),
        "PLAN-TEST", 8, "UAH", 30
    )
    with caplog.at_level("INFO", logger="bot"):
        asyncio.run(on_status(FakeCallbackQuery(user_id=456, data="sub:status"), FakePoolStatusOK(row)))
    logs2 = [rec.getMessage() for rec in caplog.records if rec.name == "bot"]
    assert any(("event=status" in m) and ("bot_id=1" in m) and ("user_id=456" in m) for m in logs2), \
        "Ожидался лог event=status с bot_id и user_id"

    caplog.clear()

    # 3) on_pay (успех)
    cb = FakeCallbackQuery(user_id=789, data="pay:42")
    session = FakeSessionOK()
    with caplog.at_level("INFO", logger="bot"):
        asyncio.run(on_pay(cb, session))
    logs3 = [rec.getMessage() for rec in caplog.records if rec.name == "bot"]
    assert any(("event=create_invoice_success" in m) and ("bot_id=1" in m)
               and ("user_id=789" in m) and ("plan_id=42" in m) for m in logs3), \
        "Ожидался лог event=create_invoice_success с bot_id/user_id/plan_id"
