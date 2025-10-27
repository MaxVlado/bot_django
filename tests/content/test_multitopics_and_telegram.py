# tests/content/test_multitopics_and_telegram.py
import pytest
from datetime import time, timedelta
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

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
from content.telegram_sender import TelegramContentSender


@covers("C4.1")
@pytest.mark.django_db
def test_multiple_active_topics_independent_progress():
    """Пользователь с несколькими активными топиками: прогресс независим"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    
    # Два разных плана с разными топиками
    plan1 = Plan.objects.create(bot_id=1, name="Plan A", price=100, duration_days=30)
    plan2 = Plan.objects.create(bot_id=1, name="Plan B", price=200, duration_days=30)
    
    # ИСПРАВЛЕНО: Разные sequence_number для топиков одного бота
    topic1 = ContentTopic.objects.create(bot=bot, title="Курс A", sequence_number=1, duration_days=30)
    topic2 = ContentTopic.objects.create(bot=bot, title="Курс B", sequence_number=2, duration_days=30)
    
    TopicPlanAccess.objects.create(topic=topic1, plan=plan1, month_number=1)
    TopicPlanAccess.objects.create(topic=topic2, plan=plan2, month_number=1)
    
    # Две активные подписки (разные планы, поэтому нет конфликта unique_together)
    sub1 = Subscription.objects.create(
        user=user, plan=plan1, bot_id=1, status="active",
        starts_at=timezone.now() - timedelta(days=5),
        expires_at=timezone.now() + timedelta(days=25)
    )
    sub2 = Subscription.objects.create(
        user=user, plan=plan2, bot_id=1, status="active",
        starts_at=timezone.now() - timedelta(days=2),
        expires_at=timezone.now() + timedelta(days=28)
    )
    
    # Прогресс по каждому топику
    progress1 = UserContentProgress.objects.create(
        user=user, topic=topic1, subscription=sub1,
        current_lesson_number=6,  # топик 1 на дне 6
        started_at=sub1.starts_at
    )
    progress2 = UserContentProgress.objects.create(
        user=user, topic=topic2, subscription=sub2,
        current_lesson_number=3,  # топик 2 на дне 3
        started_at=sub2.starts_at
    )
    
    # Проверяем что прогресс независим
    assert progress1.current_lesson_number == 6
    assert progress2.current_lesson_number == 3
    assert progress1.topic != progress2.topic


@covers("C4.2")
@pytest.mark.django_db
def test_one_plan_multiple_topics_different_months():
    """Один план дает доступ к нескольким топикам (разные month_number)"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    plan = Plan.objects.create(bot_id=1, name="Multi Plan", price=300, duration_days=30)
    
    # План дает доступ к 3 топикам по месяцам
    topic1 = ContentTopic.objects.create(bot=bot, title="Модуль 1", sequence_number=1, duration_days=30)
    topic2 = ContentTopic.objects.create(bot=bot, title="Модуль 2", sequence_number=2, duration_days=30)
    topic3 = ContentTopic.objects.create(bot=bot, title="Модуль 3", sequence_number=3, duration_days=30)
    
    TopicPlanAccess.objects.create(topic=topic1, plan=plan, month_number=1)
    TopicPlanAccess.objects.create(topic=topic2, plan=plan, month_number=2)
    TopicPlanAccess.objects.create(topic=topic3, plan=plan, month_number=3)
    
    # Проверяем связи
    assert plan.content_topics.count() == 3
    
    # Проверяем что можно получить топик для конкретного месяца
    access_m1 = TopicPlanAccess.objects.get(plan=plan, month_number=1)
    assert access_m1.topic == topic1
    
    access_m2 = TopicPlanAccess.objects.get(plan=plan, month_number=2)
    assert access_m2.topic == topic2


@covers("C5.1")
@pytest.mark.django_db
def test_text_post_uses_send_message():
    """post_type='text': использовать send_message"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    
    # Создаем текстовый пост
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    TopicPlanAccess.objects.create(topic=topic, plan=plan, month_number=1)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1)
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time=time(7, 55))
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Текстовый пост",
        content="Только текст без медиа",
        send_time=time(7, 55)
    )
    
    assert post.post_type == "text"
    
    # Мокаем Telegram API
    class FakeBotAPI:
        def __init__(self):
            self.calls = []
        
        def send_message(self, chat_id, text, **kwargs):
            self.calls.append({'method': 'send_message', 'text': text})
        
        def send_audio(self, chat_id, audio, caption=None, **kwargs):
            self.calls.append({'method': 'send_audio', 'caption': caption})
        
        def send_video(self, chat_id, video, caption=None, **kwargs):
            self.calls.append({'method': 'send_video', 'caption': caption})
        
        def send_photo(self, chat_id, photo, caption=None, **kwargs):
            self.calls.append({'method': 'send_photo', 'caption': caption})
    
    bot_api = FakeBotAPI()
    sender = TelegramContentSender(bot_api)
    
    sender.send_post(user.user_id, post)
    
    # Должен использоваться send_message
    assert len(bot_api.calls) == 1
    assert bot_api.calls[0]['method'] == 'send_message'
    assert bot_api.calls[0]['text'] == "Только текст без медиа"


@covers("C5.2")
@pytest.mark.django_db
def test_audio_post_uses_send_audio_with_caption():
    """post_type='audio': использовать send_audio с caption"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1)
    phase = Phase.objects.create(bot=bot, slug="voice", title="Голосовое", default_time=time(7, 57))
    
    audio_file = SimpleUploadedFile("audio.mp3", b"audio content", content_type="audio/mpeg")
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Аудио пост",
        content="Текст как caption",
        media_file=audio_file,
        send_time=time(7, 57)
    )
    
    assert post.post_type == "audio"
    
    class FakeBotAPI:
        def __init__(self):
            self.calls = []
        
        def send_audio(self, chat_id, audio, caption=None, **kwargs):
            self.calls.append({'method': 'send_audio', 'caption': caption})
    
    bot_api = FakeBotAPI()
    sender = TelegramContentSender(bot_api)
    
    sender.send_post(user.user_id, post)
    
    # Должен использоваться send_audio с caption
    assert len(bot_api.calls) == 1
    assert bot_api.calls[0]['method'] == 'send_audio'
    assert bot_api.calls[0]['caption'] == "Текст как caption"


@covers("C5.3")
@pytest.mark.django_db
def test_video_post_uses_send_video_with_caption():
    """post_type='video': использовать send_video с caption"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1)
    phase = Phase.objects.create(bot=bot, slug="meditation", title="Медиация", default_time=time(19, 0))
    
    video_file = SimpleUploadedFile("video.mp4", b"video content", content_type="video/mp4")
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Видео медитация",
        content="Описание видео",
        media_file=video_file,
        send_time=time(19, 0)
    )
    
    assert post.post_type == "video"
    
    class FakeBotAPI:
        def __init__(self):
            self.calls = []
        
        def send_video(self, chat_id, video, caption=None, **kwargs):
            self.calls.append({'method': 'send_video', 'caption': caption})
    
    bot_api = FakeBotAPI()
    sender = TelegramContentSender(bot_api)
    
    sender.send_post(user.user_id, post)
    
    assert len(bot_api.calls) == 1
    assert bot_api.calls[0]['method'] == 'send_video'
    assert bot_api.calls[0]['caption'] == "Описание видео"


@covers("C5.4")
@pytest.mark.django_db
def test_photo_post_uses_send_photo_with_caption():
    """post_type='photo': использовать send_photo с caption"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="user1")
    
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1)
    phase = Phase.objects.create(bot=bot, slug="task", title="Задание", default_time=time(8, 4))
    
    photo_file = SimpleUploadedFile("photo.jpg", b"photo content", content_type="image/jpeg")
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Фото задание",
        content="Подпись к фото",
        media_file=photo_file,
        send_time=time(8, 4)
    )
    
    assert post.post_type == "photo"
    
    class FakeBotAPI:
        def __init__(self):
            self.calls = []
        
        def send_photo(self, chat_id, photo, caption=None, **kwargs):
            self.calls.append({'method': 'send_photo', 'caption': caption})
    
    bot_api = FakeBotAPI()
    sender = TelegramContentSender(bot_api)
    
    sender.send_post(user.user_id, post)
    
    assert len(bot_api.calls) == 1
    assert bot_api.calls[0]['method'] == 'send_photo'
    assert bot_api.calls[0]['caption'] == "Подпись к фото"