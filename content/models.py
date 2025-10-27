# content/models.py
import os
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Bot, TelegramUser
from subscriptions.models import Plan, Subscription


class ContentTopic(models.Model):
    """Курс/Топик (например, 'ВОЗЬМИ МЕНЯ НА РУЧКИ - модуль 1')"""
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name='content_topics')
    
    title = models.CharField(max_length=500, help_text="Название топика")
    description = models.TextField(blank=True, help_text="Описание курса")
    
    # Длительность и последовательность
    duration_days = models.PositiveIntegerField(default=30, help_text="Продолжительность курса в днях")
    sequence_number = models.PositiveIntegerField(default=1, help_text="Номер топика в последовательности (1,2,3...)")
    
    # Связь с планами через M2M
    plans = models.ManyToManyField(
        Plan, 
        through='TopicPlanAccess', 
        related_name='content_topics',
        help_text="Планы, дающие доступ к этому топику"
    )
    
    # Медиа
    cover_image = models.FileField(
        upload_to='content/covers/', 
        blank=True, 
        null=True,
        help_text="Обложка курса"
    )
    
    enabled = models.BooleanField(default=True, help_text="Курс активен")
    sort_order = models.IntegerField(default=0, help_text="Порядок сортировки")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content_topics'
        ordering = ['sequence_number', 'sort_order']
        indexes = [
            models.Index(fields=['bot', 'enabled']),
            models.Index(fields=['sequence_number']),
        ]
        unique_together = [('bot', 'sequence_number')]
        verbose_name = 'Топик курса'
        verbose_name_plural = 'Топики курсов'
    
    def __str__(self):
        return f"[{self.sequence_number}] {self.title}"


class TopicPlanAccess(models.Model):
    """Связь: Какие топики доступны в каком плане и в какой последовательности"""
    topic = models.ForeignKey(ContentTopic, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    
    # Порядок топиков внутри плана (1-й месяц, 2-й месяц...)
    month_number = models.PositiveIntegerField(
        default=1, 
        help_text="Номер месяца подписки (1=первый месяц, 2=второй...)"
    )
    
    sort_order = models.IntegerField(default=0)
    enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'content_topic_plan_access'
        ordering = ['month_number', 'sort_order']
        unique_together = [('plan', 'month_number')]
        verbose_name = 'Доступ к топику'
        verbose_name_plural = 'Доступы к топикам'
        indexes = [
            models.Index(fields=['plan', 'month_number']),
        ]
    
    def __str__(self):
        return f"{self.plan.name} - Месяц {self.month_number}: {self.topic.title}"


class Phase(models.Model):
    """Фазы дня с дефолтным временем (тема дня, голосовое, задание, медиация, итог)"""
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name='content_phases')
    
    slug = models.SlugField(
        max_length=50, 
        help_text="Уникальный идентификатор (thema, voice, task, meditation, summary)"
    )
    title = models.CharField(max_length=255, help_text="Название фазы")
    
    default_time = models.TimeField(help_text="Время показа по умолчанию")
    
    sort_order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content_phases'
        ordering = ['sort_order', 'default_time']
        unique_together = [('bot', 'slug')]
        indexes = [
            models.Index(fields=['bot', 'slug']),
        ]
        verbose_name = 'Фаза дня'
        verbose_name_plural = 'Фазы дня'
    
    def __str__(self):
        return f"{self.title} ({self.default_time})"


class ContentLesson(models.Model):
    """Урок/День курса (группирует посты по дням)"""
    topic = models.ForeignKey(
        ContentTopic, 
        on_delete=models.CASCADE, 
        related_name='lessons'
    )
    
    lesson_number = models.PositiveIntegerField(help_text="Номер урока/дня (1-30)")
    title = models.CharField(
        max_length=255, 
        blank=True, 
        help_text="Название урока (например, 'День 20')"
    )
    
    enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content_lessons'
        ordering = ['lesson_number']
        unique_together = [('topic', 'lesson_number')]
        indexes = [
            models.Index(fields=['topic', 'lesson_number']),
        ]
        verbose_name = 'Урок'
        verbose_name_plural = 'Уроки'
    
    def __str__(self):
        display_title = self.title or f"День {self.lesson_number}"
        return f"{self.topic.title} - {display_title}"


class ContentPost(models.Model):
    """Пост контента (текст, аудио, видео, фото)"""
    
    POST_TYPE_CHOICES = [
        ('text', 'Текст'),
        ('audio', 'Аудио'),
        ('video', 'Видео'),
        ('photo', 'Фото'),
    ]
    
    lesson = models.ForeignKey(
        ContentLesson, 
        on_delete=models.CASCADE, 
        related_name='posts'
    )
    phase = models.ForeignKey(
        Phase, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='posts',
        help_text="Фаза дня (определяет время по умолчанию)"
    )
    
    title = models.CharField(max_length=500, help_text="Заголовок поста")
    
    # Контент
    content = models.TextField(
        blank=True, 
        help_text="Текстовое содержимое или caption к медиа"
    )
    media_file = models.FileField(
        upload_to='content/media/',
        blank=True,
        null=True,
        help_text="Медиа файл (audio/video/photo)"
    )
    
    # Тип поста (определяется автоматически)
    post_type = models.CharField(
        max_length=10,
        choices=POST_TYPE_CHOICES,
        default='text',
        editable=False,
        help_text="Тип поста (определяется автоматически)"
    )
    
    # Время отправки
    send_time = models.TimeField(
        help_text="Время отправки поста (конкретное или из phase.default_time)"
    )
    
    sort_order = models.IntegerField(default=0, help_text="Порядок сортировки постов в дне")
    enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content_posts'
        ordering = ['lesson__lesson_number', 'send_time', 'sort_order']
        indexes = [
            models.Index(fields=['lesson', 'send_time', 'enabled']),
            models.Index(fields=['lesson', 'phase']),
        ]
        verbose_name = 'Пост'
        verbose_name_plural = 'Посты'
    
    def __str__(self):
        return f"{self.lesson} - {self.title} ({self.post_type})"
    
    def clean(self):
        """Валидация: должен быть content ИЛИ media_file"""
        if not self.content and not self.media_file:
            raise ValidationError(
                "Пост должен содержать текстовое содержимое (content) "
                "или медиа файл (media_file), или оба сразу."
            )
    
    def _detect_post_type(self):
        """Автоматическое определение типа поста по медиа файлу"""
        if not self.media_file:
            return 'text'
        
        # Получаем расширение файла
        file_name = self.media_file.name
        ext = os.path.splitext(file_name)[1].lower()
        
        # Определяем тип по расширению
        audio_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.mpeg', '.mpg']
        photo_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        
        if ext in audio_extensions:
            return 'audio'
        elif ext in video_extensions:
            return 'video'
        elif ext in photo_extensions:
            return 'photo'
        else:
            # Если неизвестное расширение, пытаемся по content_type
            if hasattr(self.media_file, 'content_type'):
                content_type = self.media_file.content_type or ''
                if content_type.startswith('audio/'):
                    return 'audio'
                elif content_type.startswith('video/'):
                    return 'video'
                elif content_type.startswith('image/'):
                    return 'photo'
            
            # По умолчанию считаем текстом
            return 'text'
    
    def save(self, *args, **kwargs):
        """Автоопределение post_type при сохранении"""
        self.post_type = self._detect_post_type()
        super().save(*args, **kwargs)


class UserContentProgress(models.Model):
    """Прогресс пользователя по курсу"""
    user = models.ForeignKey(
        TelegramUser, 
        on_delete=models.CASCADE,
        related_name='content_progress'
    )
    topic = models.ForeignKey(
        ContentTopic, 
        on_delete=models.CASCADE,
        related_name='user_progress'
    )
    subscription = models.ForeignKey(
        Subscription, 
        on_delete=models.CASCADE,
        related_name='content_progress',
        help_text="Подписка, по которой доступен курс"
    )
    
    # Прогресс
    current_lesson_number = models.PositiveIntegerField(
        default=1,
        help_text="Текущий урок/день (1-30)"
    )
    
    # Отслеживание отправки
    last_post_sent = models.ForeignKey(
        ContentPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Последний отправленный пост"
    )
    last_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Когда был отправлен последний пост"
    )
    
    # Статус
    started_at = models.DateTimeField(help_text="Когда пользователь начал курс")
    completed = models.BooleanField(
        default=False,
        help_text="Курс завершен"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Когда курс был завершен"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content_user_progress'
        ordering = ['-started_at']
        unique_together = [('user', 'topic', 'subscription')]
        indexes = [
            models.Index(fields=['user', 'topic']),
            models.Index(fields=['subscription', 'completed']),
            models.Index(fields=['current_lesson_number']),
        ]
        verbose_name = 'Прогресс пользователя'
        verbose_name_plural = 'Прогресс пользователей'
    
    def __str__(self):
        status = "завершен" if self.completed else f"день {self.current_lesson_number}"
        return f"{self.user} - {self.topic.title} ({status})"
    
    def mark_completed(self):
        """Отметить курс как завершенный"""
        self.completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['completed', 'completed_at', 'updated_at'])