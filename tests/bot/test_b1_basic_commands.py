"""
Тесты базовых команд бота.

Покрываем сценарии:
- B1.1 — /start: показ главного меню без ошибок
- B5.1 — is_blocked=True: доступ запрещён для любых действий
"""
import asyncio
import pytest

# если aiogram не установлен — тест будет пропущен (а не красный)
aiogram = pytest.importorskip("aiogram")  # noqa: F401

# Импортируем хендлер из бота
from bot.subscriptions import cmd_start  # noqa: E402


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
    """Минимальный мок asyncpg.Pool (для проверки блокировки пользователя)."""
    def __init__(self, blocked: bool = False):
        self._blocked = blocked

    async def fetchval(self, *_args, **_kwargs):
        # bot.main: SELECT is_blocked FROM telegram_users WHERE user_id=$1
        return self._blocked


@pytest.mark.covers("B1.1")
def test_start_shows_main_menu_when_not_blocked():
    """B1.1: /start должен показать главное меню для неблокированного пользователя."""
    msg = FakeMessage(user_id=123456)
    pool = FakePool(blocked=False)

    asyncio.run(cmd_start(msg, pool))

    assert msg.last_text is not None, "Сообщение должно быть отправлено"
    assert "Привет" in msg.last_text or "меню" in msg.last_text
    # Клавиатура должна быть inline и не пустая
    assert msg.last_markup is not None
    assert hasattr(msg.last_markup, "inline_keyboard")
    assert len(msg.last_markup.inline_keyboard) >= 1


@pytest.mark.covers("B5.1")
def test_start_rejects_when_blocked():
    """B5.1: /start должен отказать в доступе заблокированному пользователю (is_blocked=True)."""
    msg = FakeMessage(user_id=777)
    pool = FakePool(blocked=True)

    asyncio.run(cmd_start(msg, pool))

    assert msg.last_text is not None
    assert "Доступ запрещён" in msg.last_text
