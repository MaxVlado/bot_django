# leads/setup_commands.py
"""
Команды для быстрой настройки Lead Bot через Django shell.

Использование:
    python manage.py shell < leads/setup_commands.py

Или копировать команды в Django shell:
    python manage.py shell
"""

from django.contrib.auth.models import User, Permission, Group
from core.models import Bot
from leads.models import LeadBotConfig

# ============================================================
# 1. Создание группы с правами для менеджеров заявок
# ============================================================

# Создать группу "Lead Managers"
lead_managers_group, created = Group.objects.get_or_create(name='Lead Managers')

if created:
    print("✅ Группа 'Lead Managers' создана")
else:
    print("ℹ️  Группа 'Lead Managers' уже существует")

# Назначить права группе
permissions = [
    'can_view_leads',
    'can_manage_lead_bot',
]

for perm_codename in permissions:
    try:
        perm = Permission.objects.get(codename=perm_codename)
        lead_managers_group.permissions.add(perm)
        print(f"✅ Право '{perm_codename}' добавлено в группу")
    except Permission.DoesNotExist:
        print(f"⚠️  Право '{perm_codename}' не найдено. Возможно, нужно применить миграции.")


# ============================================================
# 2. Добавление пользователя в группу (ПРИМЕР)
# ============================================================

# Раскомментируйте и измените username на нужного пользователя:
"""
try:
    user = User.objects.get(username='your_manager_username')
    user.groups.add(lead_managers_group)
    print(f"✅ Пользователь '{user.username}' добавлен в группу 'Lead Managers'")
except User.DoesNotExist:
    print("⚠️  Пользователь не найден")
"""


# ============================================================
# 3. Создание конфигурации Lead Bot (ПРИМЕР)
# ============================================================

# Раскомментируйте и настройте под свой бот:
"""
try:
    bot = Bot.objects.get(bot_id=YOUR_BOT_ID)  # Замените YOUR_BOT_ID на реальный ID
    
    config, created = LeadBotConfig.objects.get_or_create(
        bot=bot,
        defaults={
            'notification_email': 'admin@example.com',  # Замените на ваш email
            'admin_user_id': 123456789,  # Замените на ваш Telegram user_id
        }
    )
    
    if created:
        print(f"✅ Конфигурация Lead Bot для @{bot.username} создана")
    else:
        print(f"ℹ️  Конфигурация Lead Bot для @{bot.username} уже существует")
        
except Bot.DoesNotExist:
    print("⚠️  Бот не найден. Создайте бота в админке сначала.")
"""


# ============================================================
# 4. Информация о созданных объектах
# ============================================================

print("\n" + "="*60)
print("ИНФОРМАЦИЯ О НАСТРОЙКЕ")
print("="*60)

# Показать все группы и их права
print("\n📋 Группы и права:")
for group in Group.objects.filter(name__icontains='lead'):
    print(f"\n  Группа: {group.name}")
    perms = group.permissions.all()
    if perms:
        for perm in perms:
            print(f"    - {perm.codename}")
    else:
        print("    (нет прав)")

# Показать пользователей в группе
print("\n👥 Пользователи в группе 'Lead Managers':")
users_in_group = User.objects.filter(groups__name='Lead Managers')
if users_in_group:
    for user in users_in_group:
        print(f"  - {user.username} ({user.email})")
else:
    print("  (пусто)")

# Показать конфигурации Lead Bot
print("\n⚙️  Конфигурации Lead Bot:")
configs = LeadBotConfig.objects.all()
if configs:
    for config in configs:
        print(f"\n  Бот: @{config.bot.username} (ID: {config.bot.bot_id})")
        print(f"    Email: {config.notification_email or 'не указан'}")
        print(f"    Admin ID: {config.admin_user_id or 'не указан'}")
else:
    print("  (нет конфигураций)")

print("\n" + "="*60)
print("ГОТОВО!")
print("="*60)
print("""
СЛЕДУЮЩИЕ ШАГИ:

1. Если нужно добавить пользователя в группу:
   - Зайдите в админку Django
   - Users → выберите пользователя
   - Groups → добавьте 'Lead Managers'

2. Если нужно создать конфигурацию бота:
   - Зайдите в админку Django
   - Настройки Lead Bot → Add
   - Выберите бота, укажите email и admin_user_id

3. Запустите бота:
   python bot_runner_aiogram.py --bot-id <BOT_ID>

4. Проверьте работу:
   - Напишите боту /start
   - Пройдите весь процесс заполнения заявки
   - Проверьте админку и email/telegram уведомления
""")
