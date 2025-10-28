# content/scheduler.py
import logging
from typing import Optional
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.db import models  # Импорт для Q объектов

from core.models import TelegramUser
from subscriptions.models import SubscriptionStatus
from .models import UserContentProgress, ContentPost

logger = logging.getLogger(__name__)


def send_scheduled_content(
    bot_id: int,
    bot_api,
    current_time: Optional[datetime] = None
) -> int:
    """
    Отправка запланированного контента пользователям.
    
    Логика:
    1. Находим все активные UserContentProgress для бота
    2. Для каждого прогресса:
       - Проверяем подписку (активна?)
       - Проверяем пользователя (не заблокирован?)
       - Вычисляем текущий день курса
       - Находим посты для отправки
       - Отправляем через bot_api
       - Обновляем прогресс
       - Проверяем завершение курса
    
    Args:
        bot_id: ID бота
        bot_api: API для отправки сообщений в Telegram
        current_time: Текущее время (для тестов)
    
    Returns:
        Количество отправленных постов
    """
    if current_time is None:
        current_time = timezone.now()
    
    # Находим все активные прогрессы для данного бота
    progress_list = UserContentProgress.objects.filter(
        topic__bot__bot_id=bot_id,
        completed=False
    ).select_related(
        'user', 'topic', 'subscription', 'last_post_sent'
    ).prefetch_related(
        'topic__lessons__posts'
    )
    
    sent_count = 0
    
    for progress in progress_list:
        try:
            sent = _process_user_progress(progress, bot_api, current_time)
            sent_count += sent
        except Exception as e:
            logger.error(
                f"Error processing progress {progress.id} for user {progress.user.user_id}: {e}",
                exc_info=True
            )
    
    logger.info(f"Scheduler finished: sent {sent_count} posts for bot {bot_id}")
    return sent_count


@transaction.atomic
def _process_user_progress(
    progress: UserContentProgress,
    bot_api,
    current_time: datetime
) -> int:
    """
    Обработка прогресса одного пользователя.
    
    Returns:
        Количество отправленных постов
    """
    user = progress.user
    subscription = progress.subscription
    topic = progress.topic
    
    # 1. Проверка: пользователь не заблокирован
    if user.is_blocked:
        logger.debug(f"User {user.user_id} is blocked, skipping")
        return 0
    
    # 2. Проверка: подписка активна
    if subscription.status != SubscriptionStatus.ACTIVE:
        logger.debug(f"Subscription {subscription.id} is not active, skipping")
        return 0
    
    # 3. Вычисляем текущий день курса
    # ИСПРАВЛЕНО: используем timezone-aware datetime для started_at
    if progress.started_at.tzinfo is None:
        started_at_aware = timezone.make_aware(progress.started_at)
    else:
        started_at_aware = progress.started_at
    
    days_since_start = (current_time.date() - started_at_aware.date()).days
    current_day = days_since_start + 1
    
    logger.debug(
        f"User {user.user_id}: days_since_start={days_since_start}, "
        f"current_day={current_day}, started_at={started_at_aware.date()}, "
        f"current_date={current_time.date()}"
    )
    
    # Проверка: день в пределах курса
    if current_day > topic.duration_days:
        logger.debug(f"User {user.user_id} beyond course duration (day {current_day} > {topic.duration_days})")
        
        # Отмечаем как завершенный
        if not progress.completed:
            progress.mark_completed()
        
        return 0
    
    # 4. Обновляем current_lesson_number если нужно
    if progress.current_lesson_number != current_day:
        logger.info(
            f"Updating lesson number for user {user.user_id}: "
            f"{progress.current_lesson_number} -> {current_day}"
        )
        progress.current_lesson_number = current_day
        progress.save(update_fields=['current_lesson_number', 'updated_at'])
    
    # 5. Находим урок для текущего дня
    try:
        from .models import ContentLesson
        lesson = ContentLesson.objects.get(
            topic=topic,
            lesson_number=current_day,
            enabled=True
        )
    except ContentLesson.DoesNotExist:
        logger.debug(f"Lesson {current_day} not found for topic {topic.id}")
        return 0
    
    # 6. Находим посты для отправки
    posts_query = lesson.posts.filter(
        enabled=True,
        send_time__lte=current_time.time()  # время поста <= текущее время
    ).order_by('send_time', 'sort_order')
    
    # 7. Исключаем уже отправленные посты
    if progress.last_post_sent_id:
        # ИСПРАВЛЕНО: Просто исключаем посты с ID <= last_post_sent_id
        # Это работает т.к. посты отправляются по порядку (send_time, sort_order)
        posts_to_send = posts_query.filter(id__gt=progress.last_post_sent_id)
    else:
        posts_to_send = posts_query
    
    # 8. Отправляем посты
    sent_count = 0
    last_sent_post = None
    
    for post in posts_to_send:
        try:
            _send_post_to_user(user, post, bot_api)
            sent_count += 1
            last_sent_post = post
            
            logger.info(f"Sent post {post.id} ({post.title}) to user {user.user_id}")
        
        except Exception as e:
            logger.error(f"Failed to send post {post.id} to user {user.user_id}: {e}")
            # Продолжаем отправку остальных постов
    
    # 9. Обновляем прогресс
    if last_sent_post:
        progress.last_post_sent = last_sent_post
        progress.last_sent_at = current_time
        progress.save(update_fields=['last_post_sent', 'last_sent_at', 'updated_at'])
    
    # 10. Проверяем завершение курса
    if current_day >= topic.duration_days:
        # Проверяем что все посты последнего урока отправлены
        last_lesson_posts_count = lesson.posts.filter(enabled=True).count()
        
        if last_lesson_posts_count > 0:
            # Проверяем что последний пост урока отправлен
            last_lesson_post = lesson.posts.filter(enabled=True).order_by('-send_time', '-sort_order').first()
            
            # Если последний пост урока отправлен (или его время прошло)
            if last_lesson_post and last_sent_post and last_sent_post.id >= last_lesson_post.id:
                if not progress.completed:
                    progress.mark_completed()
                    logger.info(f"User {user.user_id} completed topic {topic.id}")
        else:
            # Нет постов в последнем уроке - отмечаем завершенным
            if not progress.completed:
                progress.mark_completed()
                logger.info(f"User {user.user_id} completed topic {topic.id} (no posts)")
    
    return sent_count


def _send_post_to_user(user: TelegramUser, post: ContentPost, bot_api):
    """
    Отправка одного поста пользователю через Telegram Bot API.
    
    Использует TelegramContentSender для правильного выбора метода отправки.
    """
    from .telegram_sender import TelegramContentSender
    
    sender = TelegramContentSender(bot_api)
    return sender.send_post(user.user_id, post)