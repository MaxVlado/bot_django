"""
B1.4 — «Помощь»: вывод справочного текста и возврат в меню.

Ожидание:
- Хендлер on_help редактирует сообщение с текстом помощи.
- Появляется inline-клавиатура с кнопкой «⬅ Назад».
- Колбэк подтверждается (cb.answer()).
"""
import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.main import on_help  # noqa: E402


class FakeMessage:
    def __init__(self):
        self.last_text = None
        self.last_markup = None

    async def edit_text(self, text: str, reply_markup=None, **kwargs):
        self.last_text = text
        self.last_markup = reply_markup


class FakeCallbackQuery:
    def __init__(self):
        self.data = "help:open"
        self.message = FakeMessage()
        self.answered = False

    async def answer(self, *_, **__):
        self.answered = True


@pytest.mark.covers("B1.4")
def test_help_opens_with_back_button():
    """B1.4: Нажатие «Помощь» должно отобразить текст помощи и кнопку «⬅ Назад»."""
    cb = FakeCallbackQuery()

    asyncio.run(on_help(cb))

    # Текст помощи отображён
    assert cb.message.last_text is not None
    assert "Помощь" in cb.message.last_text

    # Клавиатура с кнопкой «Назад»
    kb = cb.message.last_markup
    assert kb is not None and hasattr(kb, "inline_keyboard")
    # ищем кнопку с callback_data "ui:back" или текстом "⬅ Назад"
    has_back = any(
        (getattr(btn, "callback_data", "") == "ui:back") or (getattr(btn, "text", "") == "⬅ Назад")
        for row in kb.inline_keyboard
        for btn in row
    )
    assert has_back, "Должна быть кнопка «⬅ Назад»"

    # Колбэк подтверждён
    assert cb.answered is True
