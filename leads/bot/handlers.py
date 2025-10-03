# leads/bot/handlers.py
import logging
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from .states import LeadForm
from .keyboards import (
    get_phone_keyboard,
    get_phone_validation_keyboard,
    get_comment_question_keyboard,
    get_confirmation_keyboard,
    get_question_keyboard
)
from .utils import (
    validate_phone,
    validate_email,
    send_email_notification,
    send_telegram_notification,
    format_lead_summary
)
from leads.models import Lead, LeadBotConfig
from core.models import TelegramUser, Bot as BotModel

logger = logging.getLogger("leads.bot")

router = Router()


async def get_or_create_user(user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> TelegramUser:
    """Получить или создать пользователя в БД"""
    user, created = await sync_to_async(TelegramUser.objects.get_or_create)(
        user_id=user_id,
        defaults={
            'username': username,
            'first_name': first_name,
            'last_name': last_name
        }
    )
    if not created and (username or first_name or last_name):
        # Обновляем данные если изменились
        update_fields = []
        if username and user.username != username:
            user.username = username
            update_fields.append('username')
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            update_fields.append('first_name')
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            update_fields.append('last_name')
        
        if update_fields:
            await sync_to_async(user.save)(update_fields=update_fields)
    
    return user


async def get_bot_config(bot_id: int) -> Optional[LeadBotConfig]:
    """Получить конфигурацию бота"""
    try:
        bot_model = await sync_to_async(BotModel.objects.get)(bot_id=bot_id)
        config = await sync_to_async(lambda: bot_model.lead_config)()
        return config
    except (BotModel.DoesNotExist, LeadBotConfig.DoesNotExist):
        return None


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot_id: int):
    """Обработка команды /start - начало сбора заявки"""
    logger.info(f"User {message.from_user.id} started lead conversation")
    
    # Получаем или создаем пользователя
    user = await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    # Проверяем блокировку
    if user.is_blocked:
        await message.answer("⛔ Доступ запрещён. Обратитесь в поддержку.")
        return
    
    # Получаем конфигурацию бота
    config = await get_bot_config(bot_id)
    welcome_text = config.welcome_text if config else "Привет! Я помогу вам оставить заявку.\n\nВведите ваше имя:"
    
    # Очищаем предыдущее состояние
    await state.clear()
    
    # Сохраняем bot_id в state
    await state.update_data(bot_id=bot_id)
    
    # Запрашиваем имя
    await message.answer(welcome_text)
    await state.set_state(LeadForm.waiting_for_name)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена текущей операции"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активной операции для отмены.")
        return
    
    await state.clear()
    await message.answer(
        "Операція скасована. Щоб почати заново, натисніть /start",
        reply_markup=get_question_keyboard()
    )


@router.message(LeadForm.waiting_for_name)
async def process_name(message: Message, state: FSMContext, bot_id: int):
    """Обработка ввода имени"""
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Будь ласка, введіть коректне ім'я (мінімум 2 символи)")
        return
    
    full_name = message.text.strip()
    await state.update_data(full_name=full_name)
    
    logger.info(f"User {message.from_user.id} provided name: {full_name}")
    
    # Получаем конфигурацию для текста запроса телефона
    config = await get_bot_config(bot_id)
    phone_text = config.phone_request_text if config else "Введіть номер телефону у форматі +380... або натисніть кнопку 'Поділитися номером'"
    
    # Запрашиваем телефон
    await message.answer(
        phone_text,
        reply_markup=get_phone_keyboard()
    )
    await state.set_state(LeadForm.waiting_for_phone)


@router.message(LeadForm.waiting_for_phone, F.contact)
async def process_contact(message: Message, state: FSMContext, bot_id: int):
    """Обработка отправки контакта с номером телефона"""
    phone = message.contact.phone_number
    
    # Валидация и нормализация
    is_valid, normalized_phone = validate_phone(phone)
    
    if not is_valid:
        await message.answer(
            "❌ Номер телефону має бути у форматі +380XXXXXXXXX\n\n"
            "Спробуйте ще раз або введіть номер вручну:"
        )
        return
    
    await state.update_data(phone=normalized_phone)
    
    logger.info(f"User {message.from_user.id} provided phone via contact: {normalized_phone}")
    
    # Получаем имя из state
    data = await state.get_data()
    full_name = data.get('full_name', 'Користувач')
    
    # Получаем конфигурацию для текста валидации
    config = await get_bot_config(bot_id)
    validation_text = config.email_request_text if config else f"{full_name}, це правильний номер телефону для зв'язку з Вами?\n\nПеревірте, будь ласка"
    
    # Показываем номер с подтверждением
    validation_text = validation_text.replace("Vlad", full_name)
    await message.answer(
        f"📞 {normalized_phone}\n\n{validation_text}",
        reply_markup=get_phone_validation_keyboard()
    )
    await state.set_state(LeadForm.validating_phone)


@router.message(LeadForm.waiting_for_phone)
async def process_phone_text(message: Message, state: FSMContext, bot_id: int):
    """Обработка ввода телефона текстом"""
    if not message.text:
        await message.answer("Будь ласка, введіть номер телефону або натисніть кнопку 'Поділитися номером'")
        return
    
    phone = message.text.strip()
    
    # Валидация и нормализация
    is_valid, normalized_phone = validate_phone(phone)
    
    if not is_valid:
        await message.answer(
            "❌ Номер телефону має бути у форматі +380XXXXXXXXX\n\n"
            "Приклад: +380671234567\n\n"
            "Спробуйте ще раз:"
        )
        return
    
    await state.update_data(phone=normalized_phone)
    
    logger.info(f"User {message.from_user.id} provided phone via text: {normalized_phone}")
    
    # Получаем имя из state
    data = await state.get_data()
    full_name = data.get('full_name', 'Користувач')
    
    # Получаем конфигурацию для текста валидации
    config = await get_bot_config(bot_id)
    validation_text = config.email_request_text if config else f"{full_name}, це правильний номер телефону для зв'язку з Вами?\n\nПеревірте, будь ласка"
    
    # Показываем номер с подтверждением
    validation_text = validation_text.replace("Vlad", full_name)
    await message.answer(
        f"📞 {normalized_phone}\n\n{validation_text}",
        reply_markup=get_phone_validation_keyboard()
    )
    await state.set_state(LeadForm.validating_phone)


@router.callback_query(LeadForm.validating_phone, F.data == "phone:confirm")
async def phone_confirmed(callback: CallbackQuery, state: FSMContext, bot_id: int):
    """Телефон подтвержден - спрашиваем про комментарий"""
    await callback.answer()
    
    # Получаем данные
    data = await state.get_data()
    full_name = data.get('full_name', 'Користувач')
    
    # Получаем конфигурацию для текста запроса комментария
    config = await get_bot_config(bot_id)
    comment_text = config.comment_request_text if config else f"{full_name}, останній крок 😊\n\nБажаєте залишити побажання, коментар чи запитання, будь ласка"
    
    comment_text = comment_text.replace("Vlad", full_name)
    
    await callback.message.edit_text(
        comment_text,
        reply_markup=get_comment_question_keyboard()
    )
    await state.set_state(LeadForm.asking_for_comment)


@router.callback_query(LeadForm.validating_phone, F.data == "phone:edit")
async def phone_edit(callback: CallbackQuery, state: FSMContext):
    """Пользователь хочет исправить телефон"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Гаразд, введіть правильний номер телефону:",
        reply_markup=None
    )
    await state.set_state(LeadForm.waiting_for_phone)


@router.callback_query(LeadForm.asking_for_comment, F.data == "comment:yes")
async def comment_yes(callback: CallbackQuery, state: FSMContext):
    """Пользователь хочет оставить комментарий"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Напишіть ваше побажання, коментар або запитання:",
        reply_markup=None
    )
    await state.set_state(LeadForm.waiting_for_comment)


@router.callback_query(LeadForm.asking_for_comment, F.data == "comment:no")
async def comment_no(callback: CallbackQuery, state: FSMContext, bot_id: int):
    """Пользователь не хочет оставлять комментарий - финальное подтверждение"""
    await callback.answer()
    
    # Сохраняем пустой комментарий
    await state.update_data(comment=None, email=None)
    
    # Показываем сводку данных
    data = await state.get_data()
    summary = format_lead_summary(
        full_name=data['full_name'],
        phone=data['phone'],
        email=data.get('email'),
        comment=data.get('comment')
    )
    
    await callback.message.edit_text(
        f"<b>Перевірте ваші дані:</b>\n\n{summary}\n\n<i>Все вірно?</i>",
        reply_markup=get_confirmation_keyboard(),
        parse_mode='HTML'
    )
    await state.set_state(LeadForm.confirming_data)


@router.message(LeadForm.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext, bot_id: int):
    """Обработка комментария"""
    if not message.text:
        await message.answer("Будь ласка, введіть текст коментаря")
        return
    
    comment = message.text.strip()
    await state.update_data(comment=comment, email=None)
    
    logger.info(f"User {message.from_user.id} provided comment")
    
    # Показываем сводку данных
    data = await state.get_data()
    summary = format_lead_summary(
        full_name=data['full_name'],
        phone=data['phone'],
        email=data.get('email'),
        comment=data.get('comment')
    )
    
    await message.answer(
        f"<b>Перевірте ваші дані:</b>\n\n{summary}\n\n<i>Все вірно?</i>",
        reply_markup=get_confirmation_keyboard(),
        parse_mode='HTML'
    )
    await state.set_state(LeadForm.confirming_data)


@router.callback_query(LeadForm.confirming_data, F.data == "confirm:yes")
async def confirm_and_save(callback: CallbackQuery, state: FSMContext, bot: Bot, bot_id: int):
    """Финальное подтверждение - сохранение в БД и отправка уведомлений"""
    await callback.answer()
    
    # Получаем все данные
    data = await state.get_data()
    full_name = data['full_name']
    phone = data['phone']
    email = data.get('email')
    comment = data.get('comment')
    
    try:
        # Получаем пользователя
        user = await sync_to_async(TelegramUser.objects.get)(user_id=callback.from_user.id)
        
        # Получаем модель бота
        bot_model = await sync_to_async(BotModel.objects.get)(bot_id=bot_id)
        
        # Создаем заявку
        lead = await sync_to_async(Lead.objects.create)(
            bot=bot_model,
            user=user,
            full_name=full_name,
            phone=phone,
            email=email,
            comment=comment,
            status='new'
        )
        
        logger.info(f"Lead #{lead.id} created for user {callback.from_user.id}")
        
        # Отправляем уведомления
        config = await get_bot_config(bot_id)
        
        # Email уведомление
        if config and config.notification_email:
            email_sent = await send_email_notification(
                lead_id=lead.id,
                full_name=full_name,
                phone=phone,
                email=email,
                comment=comment,
                recipient_email=config.notification_email
            )
            if email_sent:
                lead.email_sent = True
                await sync_to_async(lead.save)(update_fields=['email_sent'])
        
        # Telegram уведомление администратору
        if config and config.admin_user_id:
            telegram_sent = await send_telegram_notification(
                bot=bot,
                admin_user_id=config.admin_user_id,
                lead_id=lead.id,
                full_name=full_name,
                phone=phone,
                email=email,
                comment=comment
            )
            if telegram_sent:
                lead.telegram_sent = True
                await sync_to_async(lead.save)(update_fields=['telegram_sent'])
        
        # Получаем текст успеха
        success_text = config.success_text if config else "Дякуємо! Ваша заявка прийнята. З вами зв'яжуться найближчим часом."
        success_text = success_text.replace("Vlad", full_name)
        
        # Отправляем подтверждение пользователю
        await callback.message.edit_text(
            success_text,
            reply_markup=get_question_keyboard(),
            parse_mode='HTML'
        )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error saving lead for user {callback.from_user.id}: {e}")
        await callback.message.edit_text(
            "❌ Виникла помилка при збереженні заявки. Будь ласка, спробуйте ще раз або зв'яжіться з підтримкою.",
            reply_markup=None
        )
        await state.clear()


@router.callback_query(LeadForm.confirming_data, F.data == "confirm:edit")
async def confirm_edit(callback: CallbackQuery, state: FSMContext):
    """Пользователь хочет исправить данные - начинаем заново"""
    await callback.answer()
    
    await callback.message.edit_text(
        "Гаразд, почнемо заново.\n\nВведіть ваше ім'я:",
        reply_markup=None
    )
    await state.set_state(LeadForm.waiting_for_name)


@router.callback_query(F.data == "new_question")
async def new_question(callback: CallbackQuery, state: FSMContext, bot_id: int):
    """Обработка кнопки 'Є питання' - начало новой заявки"""
    await callback.answer()
    
    # Получаем конфигурацию
    config = await get_bot_config(bot_id)
    welcome_text = config.welcome_text if config else "Привет! Я помогу вам оставить заявку.\n\nВведите ваше имя:"
    
    await callback.message.edit_text(
        welcome_text,
        reply_markup=None
    )
    await state.set_state(LeadForm.waiting_for_name)


def register_handlers(dp, bot_id: int):
    """Регистрация всех handlers в dispatcher"""
    # Добавляем bot_id в middleware для всех handlers
    @router.message.middleware()
    @router.callback_query.middleware()
    async def inject_bot_id(handler, event, data):
        data['bot_id'] = bot_id
        return await handler(event, data)
    
    dp.include_router(router)

    #Логируем для отладки
    logger.info(f"Lead handlers registered for bot_id={bot_id}")