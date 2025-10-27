# content/telegram_sender.py
import logging
from typing import Optional

from .models import ContentPost

logger = logging.getLogger(__name__)


class TelegramContentSender:
    """
    Отправка контента в Telegram с правильным выбором метода API.
    
    В зависимости от post_type выбирает:
    - text -> send_message
    - audio -> send_audio (с caption)
    - video -> send_video (с caption)
    - photo -> send_photo (с caption)
    """
    
    def __init__(self, bot_api):
        """
        Args:
            bot_api: Telegram Bot API (aiogram Bot или mock)
        """
        self.bot_api = bot_api
    
    def send_post(self, user_id: int, post: ContentPost) -> bool:
        """
        Отправляет пост пользователю.
        
        Args:
            user_id: Telegram user ID
            post: Пост для отправки
        
        Returns:
            True если успешно отправлено, False при ошибке
        """
        try:
            if post.post_type == 'text':
                self._send_text_post(user_id, post)
            
            elif post.post_type == 'audio':
                self._send_audio_post(user_id, post)
            
            elif post.post_type == 'video':
                self._send_video_post(user_id, post)
            
            elif post.post_type == 'photo':
                self._send_photo_post(user_id, post)
            
            else:
                logger.error(f"Unknown post_type: {post.post_type} for post {post.id}")
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to send post {post.id} to user {user_id}: {e}", exc_info=True)
            return False
    
    def _send_text_post(self, user_id: int, post: ContentPost):
        """Отправка текстового поста через send_message"""
        self.bot_api.send_message(
            chat_id=user_id,
            text=post.content,
            parse_mode='HTML'
        )
        logger.debug(f"Sent text post {post.id} to user {user_id}")
    
    def _send_audio_post(self, user_id: int, post: ContentPost):
        """Отправка аудио через send_audio с caption"""
        if not post.media_file:
            logger.warning(f"Audio post {post.id} has no media_file, sending as text")
            self._send_text_post(user_id, post)
            return
        
        # Открываем файл для отправки
        try:
            with post.media_file.open('rb') as audio_file:
                self.bot_api.send_audio(
                    chat_id=user_id,
                    audio=audio_file,
                    caption=post.content if post.content else None,
                    parse_mode='HTML'
                )
        except FileNotFoundError:
            logger.error(f"Media file not found for post {post.id}: {post.media_file.name}")
            # Отправляем хотя бы текст
            if post.content:
                self._send_text_post(user_id, post)
        
        logger.debug(f"Sent audio post {post.id} to user {user_id}")
    
    def _send_video_post(self, user_id: int, post: ContentPost):
        """Отправка видео через send_video с caption"""
        if not post.media_file:
            logger.warning(f"Video post {post.id} has no media_file, sending as text")
            self._send_text_post(user_id, post)
            return
        
        try:
            with post.media_file.open('rb') as video_file:
                self.bot_api.send_video(
                    chat_id=user_id,
                    video=video_file,
                    caption=post.content if post.content else None,
                    parse_mode='HTML'
                )
        except FileNotFoundError:
            logger.error(f"Media file not found for post {post.id}: {post.media_file.name}")
            if post.content:
                self._send_text_post(user_id, post)
        
        logger.debug(f"Sent video post {post.id} to user {user_id}")
    
    def _send_photo_post(self, user_id: int, post: ContentPost):
        """Отправка фото через send_photo с caption"""
        if not post.media_file:
            logger.warning(f"Photo post {post.id} has no media_file, sending as text")
            self._send_text_post(user_id, post)
            return
        
        try:
            with post.media_file.open('rb') as photo_file:
                self.bot_api.send_photo(
                    chat_id=user_id,
                    photo=photo_file,
                    caption=post.content if post.content else None,
                    parse_mode='HTML'
                )
        except FileNotFoundError:
            logger.error(f"Media file not found for post {post.id}: {post.media_file.name}")
            if post.content:
                self._send_text_post(user_id, post)
        
        logger.debug(f"Sent photo post {post.id} to user {user_id}")


def send_post_to_user(user_id: int, post: ContentPost, bot_api) -> bool:
    """
    Вспомогательная функция для отправки поста.
    
    Args:
        user_id: Telegram user ID
        post: Пост для отправки
        bot_api: Telegram Bot API
    
    Returns:
        True если успешно, False при ошибке
    """
    sender = TelegramContentSender(bot_api)
    return sender.send_post(user_id, post)