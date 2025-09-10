"""
B1.2 — «Моя подписка» для незарегистрированного пользователя.

Ожидание:
- Хендлер on_status отвечает текстом о том, что подписка не найдена.
- Показывается главное меню (inline-клавиатура).
"""

import asyncio
import pytest

# если aiogram не установлен — тест будет пропущен (а не красный)
aiogram = pytest.importorskip("aiogram")  # noqa: F401

# Импорт хендлера из бота
from bot.main import on_status  # noqa: E402


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


class FakePool:
    """
    Минимальный мок asyncpg.Pool.
    Нужны:
      - fetchval(...) -> для проверки is_blocked
      - fetchrow(...) -> для получения статуса подписки (вернём None)
    """
    def __init__(self, blocked: bool = False, row=None):
        self._blocked = blocked
        self._row = row

    async def fetchval(self, *_args, **_kwargs):
        # SELECT is_blocked FROM telegram_users WHERE user_id=$1
        return self._blocked

    async def fetchrow(self, *_args, **_kwargs):
        # Запрос статуса подписки — для B1.2 вернём None (подписка не найдена)
        return self._row


@pytest.mark.covers("B1.2")
def test_status_for_unknown_user_shows_no_subscription_message():
    """B1.2: Нажатие «Моя подписка» должно сообщать об отсутствии подписки и показать меню."""
    cb = FakeCallbackQuery(user_id=123456, data="sub:status")
    pool = FakePool(blocked=False, row=None)  # не заблокирован, подписки нет

    asyncio.run(on_status(cb, pool))

    # Текст с сообщением об отсутствии подписки
    assert cb.message.last_text is not None
    assert "Подписка не найдена" in cb.message.last_text

    # Есть inline-клавиатура (главное меню)
    assert cb.message.last_markup is not None
    assert hasattr(cb.message.last_markup, "inline_keyboard")
    assert len(cb.message.last_markup.inline_keyboard) >= 1

    # Колбэк был подтверждён
    assert cb.answered is True
