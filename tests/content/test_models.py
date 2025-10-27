# tests/content/test_models.py
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from tests.scenario_cov import covers
from core.models import Bot, TelegramUser
from subscriptions.models import Plan
from content.models import (
    ContentTopic,
    TopicPlanAccess,
    Phase,
    ContentLesson,
    ContentPost,
    UserContentProgress
)


@covers("C1.1")
@pytest.mark.django_db
def test_content_topic_creation():
    """ContentTopic создается с корректными полями"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    
    topic = ContentTopic.objects.create(
        bot=bot,
        title="ВОЗЬМИ МЕНЯ НА РУЧКИ - модуль 1",
        description="Описание курса",
        duration_days=30,
        sequence_number=1,
        enabled=True,
        sort_order=10
    )
    
    assert topic.id is not None
    assert topic.title == "ВОЗЬМИ МЕНЯ НА РУЧКИ - модуль 1"
    assert topic.duration_days == 30
    assert topic.sequence_number == 1
    assert topic.enabled is True
    assert str(topic) == "[1] ВОЗЬМИ МЕНЯ НА РУЧКИ - модуль 1"


@covers("C1.2")
@pytest.mark.django_db
def test_topic_plan_access_creates_link():
    """TopicPlanAccess связывает план и топик с month_number"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    plan = Plan.objects.create(bot_id=1, name="Plan 1", price=100, duration_days=30)
    topic = ContentTopic.objects.create(
        bot=bot,
        title="Topic 1",
        duration_days=30,
        sequence_number=1
    )
    
    access = TopicPlanAccess.objects.create(
        topic=topic,
        plan=plan,
        month_number=1
    )
    
    assert access.id is not None
    assert access.topic == topic
    assert access.plan == plan
    assert access.month_number == 1
    
    # Проверка M2M связи
    assert topic in plan.content_topics.all()


@covers("C1.3")
@pytest.mark.django_db
def test_phase_creation():
    """Phase создается с slug, title, default_time"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    
    phase = Phase.objects.create(
        bot=bot,
        slug="thema",
        title="Тема дня",
        default_time="07:55:00",
        sort_order=1
    )
    
    assert phase.id is not None
    assert phase.slug == "thema"
    assert phase.title == "Тема дня"
    assert str(phase.default_time) == "07:55:00"
    assert str(phase) == "Тема дня (07:55:00)"


@covers("C1.4")
@pytest.mark.django_db
def test_content_lesson_unique_per_topic():
    """ContentLesson привязывается к топику с lesson_number (уникальность)"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    topic = ContentTopic.objects.create(
        bot=bot,
        title="Topic 1",
        duration_days=30,
        sequence_number=1
    )
    
    lesson = ContentLesson.objects.create(
        topic=topic,
        lesson_number=20,
        title="День 20"
    )
    
    assert lesson.id is not None
    assert lesson.topic == topic
    assert lesson.lesson_number == 20
    assert lesson.title == "День 20"
    assert str(lesson) == "Topic 1 - День 20"
    
    # Проверка уникальности: нельзя создать второй урок с тем же номером
    with pytest.raises(Exception):  # IntegrityError
        ContentLesson.objects.create(
            topic=topic,
            lesson_number=20,
            title="День 20 дубликат"
        )


@covers("C1.5")
@pytest.mark.django_db
def test_content_post_auto_detect_audio_type():
    """ContentPost с аудио файлом: post_type автоопределяется = 'audio'"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase = Phase.objects.create(bot=bot, slug="voice", title="Голосовое", default_time="07:57:00")
    
    # Создаем fake аудио файл
    audio_file = SimpleUploadedFile(
        "test_audio.mp3",
        b"fake audio content",
        content_type="audio/mpeg"
    )
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Аудио пост",
        content="Описание аудио",
        media_file=audio_file,
        send_time="07:57:00"
    )
    
    assert post.post_type == "audio"


@covers("C1.5")
@pytest.mark.django_db
def test_content_post_auto_detect_video_type():
    """ContentPost с видео файлом: post_type автоопределяется = 'video'"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase = Phase.objects.create(bot=bot, slug="meditation", title="Медиация", default_time="19:00:00")
    
    video_file = SimpleUploadedFile(
        "test_video.mp4",
        b"fake video content",
        content_type="video/mp4"
    )
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Видео медитация",
        content="Описание видео",
        media_file=video_file,
        send_time="19:00:00"
    )
    
    assert post.post_type == "video"


@covers("C1.5")
@pytest.mark.django_db
def test_content_post_auto_detect_photo_type():
    """ContentPost с фото файлом: post_type автоопределяется = 'photo'"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase = Phase.objects.create(bot=bot, slug="task", title="Задание", default_time="08:04:00")
    
    photo_file = SimpleUploadedFile(
        "test_photo.jpg",
        b"fake photo content",
        content_type="image/jpeg"
    )
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Фото задание",
        content="Описание фото",
        media_file=photo_file,
        send_time="08:04:00"
    )
    
    assert post.post_type == "photo"


@covers("C1.6")
@pytest.mark.django_db
def test_content_post_text_only():
    """ContentPost только с текстом: post_type='text'"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема дня", default_time="07:55:00")
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="ДЕНЬ 1. Тема дня",
        content="Только текстовое содержимое без медиа",
        send_time="07:55:00"
    )
    
    assert post.post_type == "text"
    assert not post.media_file  # Исправлено: проверяем что файл не загружен


@covers("C1.7")
@pytest.mark.django_db
def test_content_post_text_plus_media():
    """ContentPost с текстом + медиа: post_type определяется по медиа"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase = Phase.objects.create(bot=bot, slug="voice", title="Голосовое", default_time="07:57:00")
    
    audio_file = SimpleUploadedFile("audio.mp3", b"audio", content_type="audio/mpeg")
    
    post = ContentPost.objects.create(
        lesson=lesson,
        phase=phase,
        title="Голосовое с текстом",
        content="Это caption к аудио",  # Текст есть
        media_file=audio_file,           # Медиа есть
        send_time="07:57:00"
    )
    
    # post_type определяется по медиа, НЕ по content
    assert post.post_type == "audio"
    assert post.content == "Это caption к аудио"


@covers("C1.8")
@pytest.mark.django_db
def test_content_post_validation_requires_content_or_media():
    """ContentPost валидация: должен быть content ИЛИ media_file"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    lesson = ContentLesson.objects.create(topic=topic, lesson_number=1, title="День 1")
    phase = Phase.objects.create(bot=bot, slug="thema", title="Тема", default_time="07:55:00")
    
    # Попытка создать пост БЕЗ content и БЕЗ media_file
    post = ContentPost(
        lesson=lesson,
        phase=phase,
        title="Пустой пост",
        send_time="07:55:00"
    )
    
    # Должна быть ошибка валидации
    with pytest.raises(ValidationError):
        post.full_clean()


@covers("C1.9")
@pytest.mark.django_db
def test_user_content_progress_creation():
    """UserContentProgress создается с current_lesson_number=1 при старте"""
    bot = Bot.objects.create(bot_id=1, title="Test Bot", token="TOKEN")
    user = TelegramUser.objects.create(user_id=12345, username="testuser")
    plan = Plan.objects.create(bot_id=1, name="Plan", price=100, duration_days=30)
    topic = ContentTopic.objects.create(bot=bot, title="Topic", sequence_number=1, duration_days=30)
    
    from subscriptions.models import Subscription
    from django.utils import timezone
    subscription = Subscription.objects.create(
        user=user,
        plan=plan,
        bot_id=1,
        status="active",
        starts_at=timezone.now(),
        expires_at=timezone.now() + timezone.timedelta(days=30)
    )
    
    progress = UserContentProgress.objects.create(
        user=user,
        topic=topic,
        subscription=subscription,
        current_lesson_number=1,
        started_at=timezone.now()
    )
    
    assert progress.id is not None
    assert progress.current_lesson_number == 1
    assert progress.completed is False
    assert progress.last_post_sent is None