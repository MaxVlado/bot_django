# leads/models.py
from django.db import models
from django.core.validators import EmailValidator, RegexValidator
from core.models import TelegramUser, Bot


class LeadBotConfig(models.Model):
    """
    Настройки бота для сбора заявок.
    Привязка к Bot из core.
    """
    bot = models.OneToOneField(
        Bot,
        on_delete=models.CASCADE,
        related_name='lead_config',
        verbose_name='Бот'
    )
    
    # Email для уведомлений
    notification_email = models.EmailField(
        max_length=255,
        validators=[EmailValidator()],
        blank=True,
        null=True,
        help_text='Email для отправки уведомлений о новых заявках'
    )
    
    # Telegram Admin ID для уведомлений
    admin_user_id = models.BigIntegerField(
        blank=True,
        null=True,
        help_text='Telegram User ID администратора для уведомлений'
    )
    
    # Настройки текстов бота
    welcome_text = models.TextField(
        default=(
            'Привет! 👋\n\n'
            'Я помогу вам оставить заявку.\n'
            'Введите ОДНИМ СООБЩЕНИЕМ ваше имя, вопрос или пожелание, будь ласка'
        ),
        help_text='Приветственное сообщение при /start'
    )
    
    phone_request_text = models.TextField(
        default=(
            'Введите номер телефону, за яким можна зв\'язатися з Вами, будь ласка 📞\n\n'
            'Номер у форматі +380... або натисніть нижче кнопку "Поділитися номером"'
        ),
        help_text='Текст запроса телефона'
    )
    
    email_request_text = models.TextField(
        default='Vlad, це правильний номер телефону для зв\'язку з Вами?\n\nПеревірте, будь ласка',
        help_text='Текст валидации телефона и запроса email'
    )
    
    comment_request_text = models.TextField(
        default='Vlad, останній крок 😊\n\nБажаєте залишити побажання, коментар чи запитання, будь ласка',
        help_text='Текст запроса комментария'
    )
    
    success_text = models.TextField(
        default=(
            'Vlad, супер, отримали Вашу заявку 💪👍\n\n'
            'Найближчим часом з Вами зв\'яжеться координатор і відповість на всі запитання, будьте на зв\'язку😊\n\n'
            'Якщо у Вас буде питання, натисніть кнопку "Є питання" і напишіть його 👇'
        ),
        help_text='Текст успешного сохранения заявки'
    )
    
    # Метки времени
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'lead_bot_configs'
        verbose_name = 'Настройки Lead Bot'
        verbose_name_plural = 'Настройки Lead Bot'
        permissions = [
            ('can_view_leads', 'Может просматривать заявки'),
            ('can_manage_lead_bot', 'Может управлять настройками Lead Bot'),
        ]
    
    def __str__(self):
        return f"Lead Bot Config для @{self.bot.username}"


class Lead(models.Model):
    """
    Заявка от пользователя через Telegram бота.
    """
    STATUS_CHOICES = [
        ('new', 'Новая'),
        ('in_progress', 'В работе'),
        ('completed', 'Завершена'),
        ('cancelled', 'Отменена'),
    ]
    
    # Связь с ботом и пользователем
    bot = models.ForeignKey(
        Bot,
        on_delete=models.CASCADE,
        related_name='leads',
        verbose_name='Бот'
    )
    
    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name='leads',
        verbose_name='Пользователь'
    )
    
    # Данные заявки
    full_name = models.CharField(
        max_length=255,
        verbose_name='Имя'
    )
    
    phone = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r'^\+380\d{9}$',
                message='Номер должен быть в формате +380XXXXXXXXX'
            )
        ],
        verbose_name='Телефон'
    )
    
    email = models.EmailField(
        max_length=255,
        validators=[EmailValidator()],
        blank=True,
        null=True,
        verbose_name='Email'
    )
    
    comment = models.TextField(
        blank=True,
        null=True,
        verbose_name='Комментарий/Вопрос'
    )
    
    # Статус заявки
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='new',
        verbose_name='Статус'
    )
    
    # Метки времени
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')
    
    # Метка отправки уведомлений
    email_sent = models.BooleanField(default=False, verbose_name='Email отправлен')
    telegram_sent = models.BooleanField(default=False, verbose_name='Telegram уведомление отправлено')
    
    class Meta:
        db_table = 'leads'
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['bot', '-created_at']),
        ]
    
    def __str__(self):
        return f"Заявка #{self.id} - {self.full_name} ({self.phone})"
