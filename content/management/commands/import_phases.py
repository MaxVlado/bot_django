# content/management/commands/import_phases.py
from django.core.management.base import BaseCommand
from core.models import Bot
from content.models import Phase


class Command(BaseCommand):
    help = 'Импорт фаз дня из SQL дампа'

    def add_arguments(self, parser):
        parser.add_argument('--bot-id', type=int, required=True, help='ID бота для привязки')

    def handle(self, *args, **options):
        bot_id = options['bot_id']
        
        try:
            bot = Bot.objects.get(bot_id=bot_id)
        except Bot.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Bot с bot_id={bot_id} не найден'))
            return

        phases_data = [
            {'slug': 'thema', 'title': 'Тема дня', 'default_time': '07:55:00', 'sort_order': 1},
            {'slug': 'voice', 'title': 'Голосовое', 'default_time': '07:57:00', 'sort_order': 2},
            {'slug': 'task', 'title': 'Задание дня', 'default_time': '08:04:00', 'sort_order': 3},
            {'slug': 'mediation', 'title': 'Медиация', 'default_time': '19:02:00', 'sort_order': 4},
            {'slug': 'summary', 'title': 'Итог дня', 'default_time': '19:57:00', 'sort_order': 5},
        ]

        created = 0
        for data in phases_data:
            phase, is_new = Phase.objects.get_or_create(
                bot=bot,
                slug=data['slug'],
                defaults={
                    'title': data['title'],
                    'default_time': data['default_time'],
                    'sort_order': data['sort_order']
                }
            )
            if is_new:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Создана фаза: {phase.slug} - {phase.title}'))
            else:
                self.stdout.write(self.style.WARNING(f'→ Фаза уже существует: {phase.slug}'))

        self.stdout.write(self.style.SUCCESS(f'\nИтого создано: {created} из {len(phases_data)}'))