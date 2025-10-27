# tests/content/test_initialization.py
import pytest
from datetime import time
from django.utils import timezone

from tests.scenario_cov import covers
from core.models import Bot, TelegramUser
from subscriptions.models import Plan, Subscription
from content.models import (
    ContentTopic,
    TopicPlanAccess,
    Phase,
    ContentLesson,
    ContentPost,
    UserContentProgress
)
from content.services import ContentDeliveryService


@covers("C2.1")
@pytest.mark.django_db
def test_first_payment_creates_progress_for_sequence_1():
    """Первая оплата плана: создается UserContentProgress для топика sequence_number=1"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan Month", price=100, duration_days=30)
    
    # Создаем топики
    topic1 = ContentTopic.objects.create(
        bot=bot, title="Модуль 1", sequence_number=1, duration_days=30
    )
    topic2 = ContentTopic.objects.create(
        bot=bot, title="Модуль 2", sequence_number=2, duration_days=30
    )
    
    # Связываем топики с планом
    TopicPlanAccess.objects.create(topic=topic1, plan=plan, month_number=1)
    TopicPlanAccess.objects.create(topic=topic2, plan=plan, month_number=2)
    
    # Создаем подписку (первая оплата)
    subscription = Subscription.objects.create(
        user=user,
        plan=plan,
        bot_id=1,
        status="active",
        starts_at=timezone.now(),
        expires_at=timezone.now() + timezone.timedelta(days=30)
    )
    
    # Инициализируем контент
    ContentDeliveryService.initialize_user_content(user, subscription)
    
    # Проверяем что создался прогресс для топика sequence=1
    progress = UserContentProgress.objects.filter(user=user, topic=topic1).first()
    assert progress is not None
    assert progress.current_lesson_number == 1
    assert progress.subscription == subscription
    
    # Для топика sequence=2 прогресса еще нет
    progress2 = UserContentProgress.objects.filter(user=user, topic=topic2).first()
    assert progress2 is None


@covers("C2.2")
@pytest.mark.django_db
def test_second_payment_creates_progress_for_sequence_2():
    """Вторая оплата (продление): создается прогресс для топика sequence_number=2"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan Month", price=100, duration_days=30)
    
    topic1 = ContentTopic.objects.create(bot=bot, title="Модуль 1", sequence_number=1, duration_days=30)
    topic2 = ContentTopic.objects.create(bot=bot, title="Модуль 2", sequence_number=2, duration_days=30)
    
    TopicPlanAccess.objects.create(topic=topic1, plan=plan, month_number=1)
    TopicPlanAccess.objects.create(topic=topic2, plan=plan, month_number=2)
    
    # ИСПРАВЛЕНО: Создаем одну подписку (т.к. unique_together на user+plan+bot_id)
    # При продлении обновляется та же подписка
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=timezone.now() - timezone.timedelta(days=30),
        expires_at=timezone.now() + timezone.timedelta(days=30)
    )
    
    # Создаем Invoice для первого платежа (APPROVED)
    from payments.models import Invoice, PaymentStatus
    inv1 = Invoice.objects.create(
        order_reference=Invoice.generate_order_reference(1, user.user_id, plan.id),
        user=user,
        plan=plan,
        bot_id=1,
        subscription=subscription,
        amount=plan.price,
        currency='UAH',
        payment_status=PaymentStatus.APPROVED,
        paid_at=timezone.now() - timezone.timedelta(days=30)
    )
    
    # Инициализируем контент для первого платежа
    ContentDeliveryService.initialize_user_content(user, subscription)
    
    # Проверяем что создался прогресс для топика 1
    progress1 = UserContentProgress.objects.filter(user=user, topic=topic1).first()
    assert progress1 is not None
    
    # Создаем Invoice для второго платежа (продление)
    inv2 = Invoice.objects.create(
        order_reference=Invoice.generate_order_reference(1, user.user_id, plan.id),
        user=user,
        plan=plan,
        bot_id=1,
        subscription=subscription,
        amount=plan.price,
        currency='UAH',
        payment_status=PaymentStatus.APPROVED,
        paid_at=timezone.now()
    )
    
    # Инициализируем контент для второго платежа
    # Сервис должен определить что это month_number=2
    ContentDeliveryService.initialize_user_content(user, subscription)
    
    # Проверяем прогресс для топика sequence=2
    progress2 = UserContentProgress.objects.filter(user=user, topic=topic2, subscription=subscription).first()
    assert progress2 is not None
    assert progress2.current_lesson_number == 1


@covers("C2.3")
@pytest.mark.django_db
def test_late_payment_sends_all_day1_posts_immediately():
    """Оплата в 23:00 (после всех постов дня 1): отправить все посты дня 1 немедленно"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    # Создаем урок и посты дня 1
    lesson1 = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase1 = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    phase2 = Phase.objects.create(bot=bot, slug="task", title="Задание", default_time=time(8, 4))
    
    post1 = ContentPost.objects.create(
        lesson=lesson1, phase=phase1, title="Пост 1", content="Текст 1",
        send_time=time(7, 55)
    )
    post2 = ContentPost.objects.create(
        lesson=lesson1, phase=phase2, title="Пост 2", content="Текст 2",
        send_time=time(8, 4)
    )
    
    # Оплата в 23:00 (все посты дня 1 уже должны были уйти)
    late_time = timezone.now().replace(hour=23, minute=0, second=0)
    
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=late_time,
        expires_at=late_time + timezone.timedelta(days=30)
    )
    
    # Мокаем отправку
    class FakeBotAPI:
        def __init__(self):
            self.sent_messages = []
        
        def send_message(self, chat_id, text, **kwargs):
            self.sent_messages.append({'chat_id': chat_id, 'text': text})
    
    bot_api = FakeBotAPI()
    
    # Инициализируем с проверкой времени
    ContentDeliveryService.initialize_user_content(
        user, subscription, bot_api=bot_api, current_time=late_time
    )
    
    # Должны отправиться ВСЕ посты дня 1 немедленно
    assert len(bot_api.sent_messages) == 2
    assert bot_api.sent_messages[0]['text'] == "Текст 1"
    assert bot_api.sent_messages[1]['text'] == "Текст 2"


@covers("C2.4")
@pytest.mark.django_db
def test_early_payment_schedules_posts_normally():
    """Оплата в 07:00 (до первого поста дня 1): посты идут по расписанию"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    lesson1 = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    
    ContentPost.objects.create(
        lesson=lesson1, phase=phase, title="Пост 1", content="Текст 1",
        send_time=time(7, 55)
    )
    
    # Оплата в 07:00 (ДО первого поста)
    early_time = timezone.now().replace(hour=7, minute=0, second=0)
    
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=early_time,
        expires_at=early_time + timezone.timedelta(days=30)
    )
    
    class FakeBotAPI:
        def __init__(self):
            self.sent_messages = []
        
        def send_message(self, chat_id, text, **kwargs):
            self.sent_messages.append({'chat_id': chat_id, 'text': text})
    
    bot_api = FakeBotAPI()
    
    ContentDeliveryService.initialize_user_content(
        user, subscription, bot_api=bot_api, current_time=early_time
    )
    
    # Посты НЕ должны отправиться немедленно
    assert len(bot_api.sent_messages) == 0
    
    # Проверяем что прогресс создан
    progress = UserContentProgress.objects.filter(user=user, topic=topic).first()
    assert progress is not None
    assert progress.current_lesson_number == 1


@covers("C2.5")
@pytest.mark.django_db
def test_no_topic_for_month_no_progress_created():
    """Если для month_number нет топика: не создавать UserContentProgress"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    
    # Создаем только топик для месяца 1, НЕТ топика для месяца 2
    topic1 = ContentTopic.objects.create(bot=bot, title="Модуль 1", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic1, plan=plan, month_number=1)
    
    # ИСПРАВЛЕНО: Создаем одну подписку
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=timezone.now(),
        expires_at=timezone.now() + timezone.timedelta(days=30)
    )
    
    # Симулируем 3 успешных платежа через Invoice
    from payments.models import Invoice, PaymentStatus
    
    # Первый платеж
    Invoice.objects.create(
        order_reference=Invoice.generate_order_reference(1, user.user_id, plan.id),
        user=user, plan=plan, bot_id=1, subscription=subscription,
        amount=plan.price, currency='UAH',
        payment_status=PaymentStatus.APPROVED,
        paid_at=timezone.now() - timezone.timedelta(days=60)
    )
    
    # Второй платеж
    Invoice.objects.create(
        order_reference=Invoice.generate_order_reference(1, user.user_id, plan.id),
        user=user, plan=plan, bot_id=1, subscription=subscription,
        amount=plan.price, currency='UAH',
        payment_status=PaymentStatus.APPROVED,
        paid_at=timezone.now() - timezone.timedelta(days=30)
    )
    
    # Третий платеж
    Invoice.objects.create(
        order_reference=Invoice.generate_order_reference(1, user.user_id, plan.id),
        user=user, plan=plan, bot_id=1, subscription=subscription,
        amount=plan.price, currency='UAH',
        payment_status=PaymentStatus.APPROVED,
        paid_at=timezone.now()
    )
    
    # Инициализируем контент (уже 3 платежа, значит month_number=3)
    ContentDeliveryService.initialize_user_content(user, subscription)
    
    # Прогресс НЕ должен создаться, т.к. нет топика для month 3
    progress = UserContentProgress.objects.filter(user=user, subscription=subscription)
    assert progress.count() == 0