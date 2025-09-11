# ================================================================
# profiling/settings.py (финальный)
# ================================================================
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

#ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")



ALLOWED_HOSTS = [
    "dev.astrocryptovoyager.com",
    "www.dev.astrocryptovoyager.com",
    "205.196.80.158",
    "localhost"
]




# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',

    # Local apps
    'core',
    'subscriptions',
    'payments',"botops",
    # Интеграцию WayForPay делаем внутри payments (без отдельного приложения)
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Название проекта у тебя — profiling (ты делал: django-admin startproject profiling .)
ROOT_URLCONF = 'profiling.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'profiling.wsgi.application'

# Database (PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'wayforpay_db'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'password'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'ru'
TIME_ZONE = os.environ.get('TIME_ZONE', 'Europe/Kyiv')
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = '/var/www/astrocryptov_usr/data/www/dev.astrocryptovoyager.com/staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = '/var/www/astrocryptov_usr/data/www/dev.astrocryptovoyager.com/media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# WayForPay настройки (без отдельного приложения; код интеграции будет в payments/)
WAYFORPAY_MERCHANT_ACCOUNT = os.environ.get('WAYFORPAY_MERCHANT_ACCOUNT', 'test_merch_n1')
WAYFORPAY_SECRET_KEY = os.environ.get('WAYFORPAY_SECRET_KEY', 'flk3409refn54t54t*FNJRET')
WAYFORPAY_DOMAIN_NAME = os.environ.get('WAYFORPAY_DOMAIN_NAME', 'yourdomain.com')
WAYFORPAY_RETURN_URL = os.environ.get('WAYFORPAY_RETURN_URL', 'https://yourdomain.com/wayforpay/return/')
WAYFORPAY_SERVICE_URL = os.environ.get('WAYFORPAY_SERVICE_URL', 'https://yourdomain.com/wayforpay/webhook/')
WAYFORPAY_API_URL = os.environ.get('WAYFORPAY_API_URL', 'https://api.wayforpay.com/api')
WAYFORPAY_PAY_URL = os.environ.get('WAYFORPAY_PAY_URL', 'https://secure.wayforpay.com/pay')

WAYFORPAY_VERIFY_SIGNATURE = os.getenv("WAYFORPAY_VERIFY_SIGNATURE", "True").lower() == "true"


# Celery (опционально; если не используешь — параметры не мешают)
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Логирование
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': os.environ.get('LOG_LEVEL', 'INFO'),
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': os.environ.get('LOG_LEVEL', 'INFO'),
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
    },
}
