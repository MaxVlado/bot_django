"""
B5.2 — Разбан после is_blocked=True: функциональность восстанавливается.

Ожидание:
- При заблокированном пользователе /start отвечает "Доступ запрещён".
- После "разбана" (is_blocked=False) тот же /start показывает главное меню.
"""

import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.main import cmd_start  # noqa: E402


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


class FakePool:
    """Минимальный мок asyncpg.Pool: возвращает фиксированное значение is_blocked."""
    def __init__(self, blocked: bool):
        self._blocked = blocked

    async def fetchval(self, *_args, **_kwargs):
        # SELECT is_blocked FROM core_telegramuser WHERE user_id=$1
        return self._blocked


@pytest.mark.covers("B5.2")
def test_unban_restores_bot_functions():
    """B5.2: сначала блок — потом разбан — меню снова доступно."""
    user_id = 999001

    # 1) Заблокирован: ожидаем "Доступ запрещён"
    msg1 = FakeMessage(user_id)
    pool_blocked = FakePool(blocked=True)
    asyncio.run(cmd_start(msg1, pool_blocked))

    assert msg1.last_text is not None
    assert "Доступ запрещён" in msg1.last_text

    # 2) Разбан: ожидаем главное меню
    msg2 = FakeMessage(user_id)
    pool_unblocked = FakePool(blocked=False)
    asyncio.run(cmd_start(msg2, pool_unblocked))

    assert msg2.last_text is not None
    assert ("Привет" in msg2.last_text) or ("меню" in msg2.last_text)
    assert msg2.last_markup is not None
    assert hasattr(msg2.last_markup, "inline_keyboard")
    assert len(msg2.last_markup.inline_keyboard) >= 1
