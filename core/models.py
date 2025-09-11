#core/models
from django.db import models
from django.utils import timezone

class TelegramUser(models.Model):
    user_id = models.BigIntegerField(unique=True, help_text="Telegram User ID")
    username = models.CharField(max_length=255, null=True, blank=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    language_code = models.CharField(max_length=10, default='uk')
    is_blocked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'telegram_users'
        verbose_name = 'Telegram User'
        verbose_name_plural = 'Telegram Users'
        indexes = [models.Index(fields=["user_id"])]

    def __str__(self):
        uname = f"@{self.username}" if self.username else str(self.user_id)
        fname = f" ({self.first_name})" if self.first_name else ""
        return f"{uname}{fname}"

    # завязки на подписки/платежи (модели уже есть)
    def get_active_subscriptions(self, bot_id: int):
        return self.subscription_set.filter(
            bot_id=bot_id, status='active', expires_at__gt=timezone.now()
        )

    def can_create_subscription(self, bot_id: int) -> bool:
        return not self.is_blocked and not self.get_active_subscriptions(bot_id).exists()

    def get_payment_history(self, bot_id: int):
        return self.invoice_set.filter(bot_id=bot_id, payment_status='APPROVED')


class Bot(models.Model):
    """Реестр ботов и их базовые настройки."""
    bot_id = models.PositiveIntegerField(unique=True, help_text="Внутренний ID бота (совпадает с Plan.bot_id)")
    title = models.CharField(max_length=255, blank=True, help_text="Человеческое имя бота")
    username = models.CharField(max_length=255, blank=True, help_text="@username в Telegram")
    token = models.CharField(max_length=255, blank=True, help_text="HTTP API токен бота (храним аккуратно)")
    is_enabled = models.BooleanField(default=True)

    port = models.PositiveIntegerField(unique=True, null=True, blank=True,
                                       help_text="Порт для вебхука (например, 8101)")
    path = models.CharField(max_length=255, blank=True, help_text="Рабочая директория скрипта")
    log_path = models.CharField(max_length=255, blank=True, help_text="Путь к лог-файлу")
    domain_name = models.CharField(max_length=255, blank=True, help_text="Доменное имя для вебхука")
    status = models.CharField(
        max_length=20,
        choices=[("running", "Running"), ("stopped", "Stopped"), ("failed", "Failed")],
        default="stopped"
    )
    last_heartbeat = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bots"
        indexes = [models.Index(fields=["bot_id", "is_enabled"])]

    def __str__(self):
        return f"Bot#{self.bot_id} @{self.username or '-'}"
