# content/management/commands/send_content.py
"""
Management команда для ручной отправки контента.

Использование:
    python manage.py send_content --bot-id 1
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Bot
from content.scheduler import send_scheduled_content

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Отправка запланированного контента пользователям'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--bot-id',
            type=int,
            required=True,
            help='ID бота для рассылки контента'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Режим симуляции (без реальной отправки)'
        )
    
    def handle(self, *args, **options):
        bot_id = options['bot_id']
        dry_run = options.get('dry_run', False)
        
        # Проверяем что бот существует
        try:
            bot = Bot.objects.get(bot_id=bot_id)
        except Bot.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Bot with ID {bot_id} not found'))
            return
        
        self.stdout.write(f'Starting content delivery for bot: {bot.title} (ID={bot_id})')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - no actual messages will be sent'))
        
        # Для dry-run используем mock API
        if dry_run:
            class MockBotAPI:
                def __init__(self):
                    self.messages = []
                
                def send_message(self, **kwargs):
                    self.messages.append(('message', kwargs))
                
                def send_audio(self, **kwargs):
                    self.messages.append(('audio', kwargs))
                
                def send_video(self, **kwargs):
                    self.messages.append(('video', kwargs))
                
                def send_photo(self, **kwargs):
                    self.messages.append(('photo', kwargs))
            
            bot_api = MockBotAPI()
        else:
            # В реальном режиме нужно инициализировать bot API
            # TODO: Интеграция с aiogram
            self.stdout.write(self.style.ERROR(
                'Real bot API not implemented yet. Use --dry-run for testing.'
            ))
            return
        
        # Запускаем scheduler
        try:
            current_time = timezone.now()
            sent_count = send_scheduled_content(
                bot_id=bot_id,
                bot_api=bot_api,
                current_time=current_time
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'✓ Successfully sent {sent_count} posts')
            )
            
            if dry_run:
                self.stdout.write(f'Total mock calls: {len(bot_api.messages)}')
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Error during content delivery: {e}')
            )
            logger.exception('Content delivery failed')