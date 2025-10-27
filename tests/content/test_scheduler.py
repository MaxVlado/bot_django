# tests/content/test_scheduler.py
import pytest
from datetime import time, timedelta
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
from content.scheduler import send_scheduled_content


@covers("C3.1")
@pytest.mark.django_db
def test_posts_sent_strictly_by_send_time():
    """Посты дня 2+ отправляются строго по send_time"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    # День 2
    lesson2 = ContentLesson.objects.create(topic=topic, lesson_number=2, title="День 2", enabled=True)
    phase1 = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    phase2 = Phase.objects.create(bot=bot, slug="task", title="Задание", default_time=time(8, 4))
    
    post1 = ContentPost.objects.create(
        lesson=lesson2, phase=phase1, title="Пост 1", content="Текст 1",
        send_time=time(7, 55), enabled=True
    )
    post2 = ContentPost.objects.create(
        lesson=lesson2, phase=phase2, title="Пост 2", content="Текст 2",
        send_time=time(8, 4), enabled=True
    )
    
    # Подписка началась вчера
    yesterday = timezone.now() - timedelta(days=1)
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=yesterday,
        expires_at=yesterday + timedelta(days=30)
    )
    
    # ИСПРАВЛЕНО: прогресс с started_at=вчера, current_lesson_number будет обновлен scheduler'ом
    progress = UserContentProgress.objects.create(
        user=user, topic=topic, subscription=subscription,
        current_lesson_number=1,  # Начинаем с 1, scheduler обновит на 2
        started_at=yesterday
    )
    
    class FakeBotAPI:
        def __init__(self):
            self.sent_messages = []
        
        def send_message(self, chat_id, text, **kwargs):
            self.sent_messages.append({'time': timezone.now(), 'text': text})
    
    bot_api = FakeBotAPI()
    
    # Текущее время 07:56 - после первого поста, до второго
    current_time = timezone.now().replace(hour=7, minute=56)
    
    send_scheduled_content(bot_id=1, bot_api=bot_api, current_time=current_time)
    
    # Должен отправиться только первый пост (07:55)
    assert len(bot_api.sent_messages) == 1
    assert bot_api.sent_messages[0]['text'] == "Текст 1"
    
    # Второй пост еще не отправлен (время 08:04 не наступило)
    progress.refresh_from_db()
    assert progress.last_post_sent == post1
    assert progress.current_lesson_number == 2  # Обновлен на день 2


@covers("C3.2")
@pytest.mark.django_db
def test_already_sent_posts_not_resent():
    """Уже отправленные посты не отправляются повторно (идемпотентность)"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=2, title="День 2")
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    
    post = ContentPost.objects.create(
        lesson=lesson, phase=phase, title="Пост", content="Текст",
        send_time=time(7, 55), enabled=True
    )
    
    yesterday = timezone.now() - timedelta(days=1)
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=yesterday,
        expires_at=yesterday + timedelta(days=30)
    )
    
    # Прогресс с уже отправленным постом
    progress = UserContentProgress.objects.create(
        user=user, topic=topic, subscription=subscription,
        current_lesson_number=2,
        started_at=yesterday,
        last_post_sent=post,
        last_sent_at=timezone.now() - timedelta(hours=1)
    )
    
    class FakeBotAPI:
        def __init__(self):
            self.sent_messages = []
        
        def send_message(self, chat_id, text, **kwargs):
            self.sent_messages.append(text)
    
    bot_api = FakeBotAPI()
    current_time = timezone.now().replace(hour=8, minute=0)
    
    # Запускаем scheduler
    send_scheduled_content(bot_id=1, bot_api=bot_api, current_time=current_time)
    
    # Пост НЕ должен отправиться повторно
    assert len(bot_api.sent_messages) == 0


@covers("C3.3")
@pytest.mark.django_db
def test_progress_updated_after_send():
    """После отправки поста: обновить last_post_sent_id и last_sent_at"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=2, title="День 2", enabled=True)
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    
    post = ContentPost.objects.create(
        lesson=lesson, phase=phase, title="Пост", content="Текст",
        send_time=time(7, 55), enabled=True
    )
    
    yesterday = timezone.now() - timedelta(days=1)
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=yesterday,
        expires_at=yesterday + timedelta(days=30)
    )
    
    # ИСПРАВЛЕНО: начинаем с lesson_number=1, scheduler обновит
    progress = UserContentProgress.objects.create(
        user=user, topic=topic, subscription=subscription,
        current_lesson_number=1,
        started_at=yesterday
    )
    
    # До отправки
    assert progress.last_post_sent is None
    assert progress.last_sent_at is None
    
    class FakeBotAPI:
        def send_message(self, chat_id, text, **kwargs):
            pass
    
    bot_api = FakeBotAPI()
    current_time = timezone.now().replace(hour=8, minute=0)
    
    send_scheduled_content(bot_id=1, bot_api=bot_api, current_time=current_time)
    
    # После отправки
    progress.refresh_from_db()
    assert progress.last_post_sent == post
    assert progress.last_sent_at is not None
    assert progress.current_lesson_number == 2


@covers("C3.4")
@pytest.mark.django_db
def test_current_lesson_number_updates_on_next_day():
    """current_lesson_number обновляется при переходе на следующий день"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    # День 2 и День 3
    lesson2 = ContentLesson.objects.create(topic=topic, lesson_number=2, enabled=True)
    lesson3 = ContentLesson.objects.create(topic=topic, lesson_number=3, enabled=True)
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    
    ContentPost.objects.create(lesson=lesson2, phase=phase, content="День 2", send_time=time(7, 55), enabled=True)
    ContentPost.objects.create(lesson=lesson3, phase=phase, content="День 3", send_time=time(7, 55), enabled=True)
    
    # Подписка началась 2 дня назад
    two_days_ago = timezone.now() - timedelta(days=2)
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=two_days_ago,
        expires_at=two_days_ago + timedelta(days=30)
    )
    
    # ИСПРАВЛЕНО: начинаем с lesson_number=1 (или любого, scheduler обновит на 3)
    progress = UserContentProgress.objects.create(
        user=user, topic=topic, subscription=subscription,
        current_lesson_number=1,
        started_at=two_days_ago
    )
    
    class FakeBotAPI:
        def send_message(self, chat_id, text, **kwargs):
            pass
    
    bot_api = FakeBotAPI()
    current_time = timezone.now().replace(hour=8, minute=0)
    
    # Scheduler должен понять что сейчас день 3
    # (started_at было 2 дня назад, значит days_since_start=2, current_day=3)
    send_scheduled_content(bot_id=1, bot_api=bot_api, current_time=current_time)
    
    progress.refresh_from_db()
    # current_lesson_number должен обновиться на 3
    assert progress.current_lesson_number == 3


@covers("C3.5")
@pytest.mark.django_db
def test_course_completed_when_all_lessons_done():
    """Завершение курса: completed=True когда все дни пройдены"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=3)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    # Короткий курс на 3 дня
    for day in [1, 2, 3]:
        lesson = ContentLesson.objects.create(topic=topic, lesson_number=day, enabled=True)
        phase = Phase.objects.create(bot=bot, slug=f"phase{day}", title=f"День {day}", default_time=time(7, 55))
        ContentPost.objects.create(lesson=lesson, phase=phase, content=f"День {day}", send_time=time(7, 55), enabled=True)
    
    # Подписка началась 3 дня назад (курс должен завершиться)
    three_days_ago = timezone.now() - timedelta(days=3)
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=three_days_ago,
        expires_at=three_days_ago + timedelta(days=30)
    )
    
    # ИСПРАВЛЕНО: начинаем с lesson_number=1
    progress = UserContentProgress.objects.create(
        user=user, topic=topic, subscription=subscription,
        current_lesson_number=1,
        started_at=three_days_ago,
        completed=False
    )
    
    class FakeBotAPI:
        def send_message(self, chat_id, text, **kwargs):
            pass
    
    bot_api = FakeBotAPI()
    current_time = timezone.now().replace(hour=8, minute=0)
    
    # Scheduler должен определить что курс завершен
    # started_at было 3 дня назад, значит:
    # days_since_start = 3, current_day = 4
    # Но topic.duration_days = 3, значит курс завершен
    send_scheduled_content(bot_id=1, bot_api=bot_api, current_time=current_time)
    
    progress.refresh_from_db()
    # Курс завершен
    assert progress.completed is True


@covers("C3.6")
@pytest.mark.django_db
def test_blocked_user_no_posts_sent():
    """Заблокированный пользователь (is_blocked=True): посты не отправляются"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1", is_blocked=True)
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=2)
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    ContentPost.objects.create(lesson=lesson, phase=phase, content="Текст", send_time=time(7, 55))
    
    yesterday = timezone.now() - timedelta(days=1)
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="active",
        starts_at=yesterday,
        expires_at=yesterday + timedelta(days=30)
    )
    
    UserContentProgress.objects.create(
        user=user, topic=topic, subscription=subscription,
        current_lesson_number=2,
        started_at=yesterday
    )
    
    class FakeBotAPI:
        def __init__(self):
            self.sent_messages = []
        def send_message(self, chat_id, text, **kwargs):
            self.sent_messages.append(text)
    
    bot_api = FakeBotAPI()
    current_time = timezone.now().replace(hour=8, minute=0)
    
    send_scheduled_content(bot_id=1, bot_api=bot_api, current_time=current_time)
    
    # Заблокированному пользователю посты НЕ отправляются
    assert len(bot_api.sent_messages) == 0


@covers("C3.7")
@pytest.mark.django_db
def test_inactive_subscription_no_posts_sent():
    """Неактивная подписка (status!=active): посты не отправляются"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=2)
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    ContentPost.objects.create(lesson=lesson, phase=phase, content="Текст", send_time=time(7, 55))
    
    yesterday = timezone.now() - timedelta(days=1)
    subscription = Subscription.objects.create(
        user=user, plan=plan, bot_id=1, status="expired",  # неактивная
        starts_at=yesterday - timedelta(days=30),
        expires_at=yesterday
    )
    
    UserContentProgress.objects.create(
        user=user, topic=topic, subscription=subscription,
        current_lesson_number=2,
        started_at=yesterday
    )
    
    class FakeBotAPI:
        def __init__(self):
            self.sent_messages = []
        def send_message(self, chat_id, text, **kwargs):
            self.sent_messages.append(text)
    
    bot_api = FakeBotAPI()
    current_time = timezone.now().replace(hour=8, minute=0)
    
    send_scheduled_content(bot_id=1, bot_api=bot_api, current_time=current_time)
    
    # Неактивной подписке посты НЕ отправляются
    assert len(bot_api.sent_messages) == 0