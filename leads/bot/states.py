# leads/bot/states.py
from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    """Состояния для сбора данных заявки"""
    waiting_for_name = State()  # Ожидание имени
    waiting_for_phone = State()  # Ожидание телефона
    validating_phone = State()  # Валидация телефона
    waiting_for_email = State()  # Ожидание email (опционально)
    asking_for_comment = State()  # Спрашиваем, нужен ли комментарий
    waiting_for_comment = State()  # Ожидание комментария
    confirming_data = State()  # Подтверждение данных
