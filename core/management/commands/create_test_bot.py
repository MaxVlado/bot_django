from django.core.management.base import BaseCommand
from core.models import Bot
from subscriptions.models import Plan
from payments.models import MerchantConfig

class Command(BaseCommand):
    help = 'Создаёт тестового бота и план для проверки'

    def handle(self, *args, **options):
        # Создаём тестового бота
        bot, created = Bot.objects.get_or_create(
            bot_id=1,
            defaults={
                'title': 'Тестовый бот',
                'username': 'test_bot', 
                'token': '1234567890:TEST_TOKEN',
                'is_enabled': True,
            }
        )
        
        if created:
            self.stdout.write('✅ Создан тестовый бот ID=1')
        else:
            self.stdout.write('ℹ️  Тестовый бот уже существует')

        # Создаём план
        plan, created = Plan.objects.get_or_create(
            bot_id=1,
            name='Тестовый план',
            defaults={
                'price': 10,
                'currency': 'UAH',
                'duration_days': 30,
                'enabled': True,
            }
        )
        
        if created:
            self.stdout.write('✅ Создан тестовый план')
        else:
            self.stdout.write('ℹ️  Тестовый план уже существует')

        self.stdout.write(f'Plan ID: {plan.id}')
