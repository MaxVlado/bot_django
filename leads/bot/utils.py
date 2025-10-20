# leads/bot/utils.py
import re
import logging
from typing import Optional
from django.core.mail import send_mail
from django.conf import settings
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger("leads.bot")


def validate_phone(phone: str) -> tuple[bool, Optional[str]]:
    """
    Валидация номера телефона.
    
    Returns:
        (is_valid, normalized_phone)
    """
    # Убираем все символы кроме цифр и +
    phone = re.sub(r'[^\d+]', '', phone)
    
    # Проверяем формат +380XXXXXXXXX
    pattern = r'^\+380\d{9}$'
    
    if re.match(pattern, phone):
        return True, phone
    
    # Пробуем нормализовать
    if phone.startswith('380') and len(phone) == 12:
        normalized = '+' + phone
        return True, normalized
    
    if phone.startswith('0') and len(phone) == 10:
        normalized = '+38' + phone
        return True, normalized
    
    return False, None


def validate_email(email: str) -> tuple[bool, str]:
    """
    Простая валидация email.
    
    Returns:
        (True, normalized_email) если email валиден
        (False, original_email) если невалиден
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    email = email.strip().lower()
    is_valid = bool(re.match(pattern, email))
    return (is_valid, email if is_valid else email)


async def send_email_notification(
    lead_id: int,
    full_name: str,
    phone: str,
    email: Optional[str],
    comment: Optional[str],
    recipient_email: str
) -> bool:
    """
    Отправка email уведомления о новой заявке.
    
    Returns:
        True если отправлено успешно
    """
    try:
        subject = f'Новая заявка #{lead_id} от {full_name}'
        
        message = f"""
Получена новая заявка через Telegram бота!

ID заявки: {lead_id}
Имя: {full_name}
Телефон: {phone}
Email: {email or 'Не указан'}
Комментарий: {comment or 'Нет комментария'}

---
Это автоматическое уведомление из системы сбора заявок.
        """.strip()
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False
        )
        
        logger.info(f"Email notification sent for lead #{lead_id} to {recipient_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email for lead #{lead_id}: {e}")
        return False


async def send_telegram_notification(
    bot: Bot,
    admin_user_id: int,
    bot_title: str,
    lead_id: int,
    full_name: str,
    username: Optional[str],
    phone: str,
    email: Optional[str],
    comment: Optional[str]
) -> bool:
    """
    Отправка Telegram уведомления администратору о новой заявке.
    
    Returns:
        True если отправлено успешно
    """
    try:
        # Формируем username строку
        username_text = username if username else 'Не вказано'
        
        message = f"""
🤖 <b>Від бота:</b> {bot_title}

👤 <b>Ім'я:</b> {full_name}
📱 <b>Username:</b> {username_text}
📞 <b>Телефон:</b> <code>{phone}</code>
📧 <b>Email:</b> {email or 'Не вказано'}
💬 <b>Коментар:</b> {comment or 'Немає'}
        """.strip()
        
        await bot.send_message(
            chat_id=admin_user_id,
            text=message,
            parse_mode='HTML'
        )
        
        logger.info(f"Telegram notification sent for lead #{lead_id} to admin {admin_user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send Telegram notification for lead #{lead_id}: {e}")
        return False


def format_lead_summary(
    full_name: str,
    phone: str,
    email: Optional[str],
    comment: Optional[str]
) -> str:
    """
    Форматирование сводки данных заявки для отображения пользователю.
    """
    lines = [
        f"👤 <b>Ім'я:</b> {full_name}",
        f"📞 <b>Телефон:</b> {phone}",
    ]
    
    if email:
        lines.append(f"📧 <b>Email:</b> {email}")
    
    if comment:
        lines.append(f"💬 <b>Коментар:</b> {comment}")
    
    return "\n".join(lines)
