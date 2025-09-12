Полезные команды для справки
# Активация/деактивация окружения
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
deactivate

# Основные Django команды
python manage.py runserver 127.0.0.1:8001        # Запуск сервера
python manage.py makemigrations bot
python manage.py showmigrations bot  # проверкf статуса миграций.

python manage.py migrate            # Применение миграций
python manage.py createsuperuser    # Создание суперпользователя
python manage.py collectstatic --noinput  
python manage.py startapp app_name  # Создание приложения

python manage.py check              # Проверка на все

# Работа с зависимостями
pip freeze > requirements.txt       # Сохранить зависимости
`pip install -r requirements.txt `    # Установить зависимости

# test
pytest -q                           # Просто отчёт (не валим билд)
pytest -q --scenario-enforce        # Жёсткий режим (упадёт, если что-то не покрыто)
python -m pytest -q                 # при сценарии
pytest -q --scenario-report-json=coverage_scenarios.json --scenario-min-coverage=0
pytest -q tests/bot
# tree
tree -I "venv|.venv|__pycache__|migrations"
tree -I "venv|.venv|__pycache__|migrations|tests|staticfiles|docs|temp"

# linux
pip show asyncpg
pip list | grep asyncpg



# Создать файл с переменными для повторного использования
cat > /tmp/django_deploy_vars.sh << 'EOF'
export PROJECT_ROOT=/var/www/astrocryptov_usr/data/www/dev.astrocryptovoyager.com
export DOMAIN=dev.astrocryptovoyager.com
export SERVICE=dev-astrovoyager
export VIP=205.196.80.158
EOF

# Для использования в новых сессиях:
# source /tmp/django_deploy_vars.sh

/opt/venvs/dev-astrovoyager/bin/python manage.py 
