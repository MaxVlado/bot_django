# payments/notifications.py
import logging
import requests
from typing import Optional
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramNotificationService:
    """Сервис для отправки уведомлений в Telegram (синхронный, для Django)"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
        """Отправка сообщения пользователю"""
        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Telegram notification sent to user {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram notification to {chat_id}: {e}")
            return False
    
    def notify_payment_success(
        self,
        user_id: int,
        plan_name: str,
        amount: float,
        currency: str,
        expires_at: Optional[datetime] = None
    ) -> bool:
        """Уведомление об успешной оплате"""
        
        expires_txt = ""
        if expires_at:
            expires_txt = f"\n📅 Активна до: <b>{expires_at.strftime('%d.%m.%Y')}</b>"
        
        text = (
            f"✅ <b>Платёж подтверждён!</b>\n\n"
            f"💳 Оплачено: <b>{amount} {currency}</b>\n"
            f"📦 План: <b>{plan_name}</b>\n"
            f"🎯 Подписка активирована/продлена{expires_txt}"
        )
        
        return self.send_message(user_id, text)
    
    def notify_payment_declined(
        self,
        user_id: int,
        order_reference: str,
        reason: Optional[str] = None
    ) -> bool:
        """Уведомление об отклонённом платеже"""
        
        reason_txt = f"\n💬 Причина: {reason}" if reason else ""
        
        text = (
            f"❌ <b>Оплата отклонена</b>\n\n"
            f"🔖 Заказ: <code>{order_reference}</code>{reason_txt}\n\n"
            f"Попробуйте оплатить снова или свяжитесь с поддержкой."
        )
        
        return self.send_message(user_id, text)