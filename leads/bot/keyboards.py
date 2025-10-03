# leads/bot/keyboards.py
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для отправки номера телефона"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поділитися номером", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard


def get_phone_validation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения телефона"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так, все вірно", callback_data="phone:confirm"),
                InlineKeyboardButton(text="👍 Виправити", callback_data="phone:edit")
            ]
        ]
    )
    return keyboard


def get_comment_question_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для вопроса о комментарии"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так", callback_data="comment:yes"),
                InlineKeyboardButton(text="❌ Ні, питання задам коли зв'яжетесь зі мною", callback_data="comment:no")
            ]
        ]
    )
    return keyboard


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для финального подтверждения данных"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так, все вірно", callback_data="confirm:yes"),
                InlineKeyboardButton(text="👍 Виправити", callback_data="confirm:edit")
            ]
        ]
    )
    return keyboard


def get_question_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Є питання'"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Є питання", callback_data="new_question")]
        ]
    )
    return keyboard
