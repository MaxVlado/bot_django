# content/services.py
import logging
from typing import Optional
from datetime import datetime, time
from django.utils import timezone
from django.db import transaction

from core.models import TelegramUser
from subscriptions.models import Subscription
from .models import (
    ContentTopic,
    TopicPlanAccess,
    ContentLesson,
    ContentPost,
    UserContentProgress
)

logger = logging.getLogger(__name__)


class ContentDeliveryService:
    """Сервис для инициализации и доставки контента пользователям"""
    
    @staticmethod
    def _get_subscription_month_number(user: TelegramUser, subscription: Subscription) -> int:
        """
        Определяет номер месяца подписки для пользователя по данному плану.
        
        Логика:
        - Считаем количество УСПЕШНЫХ платежей (APPROVED Invoice) по этому плану
        - month_number = количество_успешных_платежей
        
        Пример:
        - Первый платеж -> month_number = 1
        - Второй платеж (продление) -> month_number = 2
        
        Примечание: 
        В системе существует unique_together(user, plan, bot_id) на Subscription,
        поэтому при продлении обновляется та же подписка, а не создается новая.
        Считаем по Invoice, т.к. каждый платеж создает новый Invoice.
        """
        from payments.models import Invoice, PaymentStatus
        
        # Считаем успешные платежи по этому плану
        approved_invoices_count = Invoice.objects.filter(
            user=user,
            plan=subscription.plan,
            bot_id=subscription.bot_id,
            payment_status=PaymentStatus.APPROVED
        ).count()
        
        # month_number = количество успешных платежей
        month_number = approved_invoices_count if approved_invoices_count > 0 else 1
        
        logger.info(
            f"User {user.user_id}, plan {subscription.plan_id}: "
            f"month_number={month_number} (approved_invoices={approved_invoices_count})"
        )
        
        return month_number
    
    @staticmethod
    def _should_send_day1_posts_immediately(
        subscription: Subscription,
        lesson: ContentLesson,
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Проверяет, нужно ли отправить все посты дня 1 немедленно.
        
        Логика:
        - Если оплата произошла ПОСЛЕ времени последнего поста дня 1
        - То все посты дня 1 должны уйти сразу
        
        Returns:
            True - если нужно отправить все посты дня 1 немедленно
            False - если посты пойдут по расписанию
        """
        if current_time is None:
            current_time = timezone.now()
        
        # Проверяем только для дня 1
        if lesson.lesson_number != 1:
            return False
        
        # Находим время последнего поста дня 1
        last_post = lesson.posts.filter(enabled=True).order_by('-send_time').first()
        
        if not last_post:
            return False
        
        # Сравниваем время оплаты с временем последнего поста
        subscription_time = current_time.time()
        last_post_time = last_post.send_time
        
        # Если оплатили после последнего поста дня - отправляем все сразу
        is_after = subscription_time > last_post_time
        
        logger.info(
            f"Day 1 immediate send check: subscription_time={subscription_time}, "
            f"last_post_time={last_post_time}, send_immediately={is_after}"
        )
        
        return is_after
    
    @staticmethod
    def _send_day1_posts_immediately(
        user: TelegramUser,
        lesson: ContentLesson,
        bot_api
    ) -> Optional[ContentPost]:
        """
        Отправляет все посты дня 1 немедленно.
        
        Returns:
            Последний отправленный пост (для сохранения в progress.last_post_sent)
        """
        if bot_api is None:
            logger.warning("bot_api is None, cannot send posts immediately")
            return None
        
        posts = lesson.posts.filter(enabled=True).order_by('send_time', 'sort_order')
        
        last_post = None
        for post in posts:
            try:
                # Отправляем через bot_api
                if post.post_type == 'text':
                    bot_api.send_message(
                        chat_id=user.user_id,
                        text=post.content,
                        parse_mode='HTML'
                    )
                elif post.post_type == 'audio':
                    bot_api.send_message(chat_id=user.user_id, text=post.content)
                elif post.post_type == 'video':
                    bot_api.send_message(chat_id=user.user_id, text=post.content)
                elif post.post_type == 'photo':
                    bot_api.send_message(chat_id=user.user_id, text=post.content)
                
                last_post = post
                logger.info(f"Sent day 1 post immediately: {post.title} to user {user.user_id}")
            
            except Exception as e:
                logger.error(f"Failed to send day 1 post {post.id}: {e}")
        
        return last_post
    
    @classmethod
    @transaction.atomic
    def initialize_user_content(
        cls,
        user: TelegramUser,
        subscription: Subscription,
        bot_api=None,
        current_time: Optional[datetime] = None
    ) -> Optional[UserContentProgress]:
        """
        Инициализация контента для пользователя после оплаты подписки.
        
        Логика:
        1. Определяем month_number подписки
        2. Находим топик для этого месяца через TopicPlanAccess
        3. Создаем UserContentProgress
        4. Если оплата после всех постов дня 1 - отправляем их немедленно
        
        Args:
            user: Пользователь
            subscription: Подписка (только что созданная/продленная)
            bot_api: API бота для отправки сообщений (опционально, для тестов)
            current_time: Текущее время (опционально, для тестов)
        
        Returns:
            UserContentProgress или None (если топика нет для данного месяца)
        """
        if current_time is None:
            current_time = timezone.now()
        
        # 1. Определяем номер месяца подписки
        month_number = cls._get_subscription_month_number(user, subscription)
        
        # 2. Находим топик для этого месяца
        try:
            access = TopicPlanAccess.objects.get(
                plan=subscription.plan,
                month_number=month_number,
                enabled=True
            )
            topic = access.topic
        except TopicPlanAccess.DoesNotExist:
            logger.info(
                f"No topic found for plan {subscription.plan_id}, "
                f"month {month_number}. Skipping content initialization."
            )
            return None
        
        # Проверяем что топик включен
        if not topic.enabled:
            logger.info(f"Topic {topic.id} is disabled. Skipping.")
            return None
        
        logger.info(
            f"Initializing content for user {user.user_id}: "
            f"topic={topic.title}, month={month_number}"
        )
        
        # 3. Создаем прогресс
        progress, created = UserContentProgress.objects.get_or_create(
            user=user,
            topic=topic,
            subscription=subscription,
            defaults={
                'current_lesson_number': 1,
                'started_at': current_time,
                'completed': False
            }
        )
        
        if not created:
            logger.warning(f"Progress already exists for user {user.user_id}, topic {topic.id}")
            return progress
        
        # 4. Проверяем нужно ли отправить посты дня 1 немедленно
        try:
            lesson1 = ContentLesson.objects.get(topic=topic, lesson_number=1, enabled=True)
        except ContentLesson.DoesNotExist:
            logger.warning(f"Lesson 1 not found for topic {topic.id}")
            return progress
        
        if cls._should_send_day1_posts_immediately(subscription, lesson1, current_time):
            logger.info(f"Sending day 1 posts immediately to user {user.user_id}")
            
            last_post = cls._send_day1_posts_immediately(user, lesson1, bot_api)
            
            if last_post:
                # Обновляем прогресс
                progress.last_post_sent = last_post
                progress.last_sent_at = current_time
                progress.current_lesson_number = 2  # переходим на день 2
                progress.save(update_fields=[
                    'last_post_sent', 
                    'last_sent_at', 
                    'current_lesson_number',
                    'updated_at'
                ])
                
                logger.info(f"Updated progress: moved to day 2 for user {user.user_id}")
        
        return progress
    
    @staticmethod
    def get_active_topics_for_user(user: TelegramUser, bot_id: int):
        """
        Получает все активные топики для пользователя.
        
        Учитывает:
        - Активные подписки пользователя
        - Существующий прогресс по топикам
        """
        # Находим все активные подписки пользователя
        active_subscriptions = Subscription.objects.filter(
            user=user,
            bot_id=bot_id,
            status='active',
            expires_at__gt=timezone.now()
        )
        
        # Находим прогресс по топикам для этих подписок
        progress_list = UserContentProgress.objects.filter(
            user=user,
            subscription__in=active_subscriptions,
            completed=False
        ).select_related('topic', 'subscription')
        
        return progress_list