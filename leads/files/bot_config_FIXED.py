# bot/config.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)
# Замените содержимое вашего bot/config.py на этот файл

from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    # Django
    django_env: str = "development"  # Значение по умолчанию
    secret_key: str
    debug: bool
    allowed_hosts: str
    time_zone: str
    log_level: str
    csrf_trusted_origins: str

    # DB
    db_name: str
    db_user: str
    db_password: str
    db_host: str
    db_port: int

    # Redis
    redis_url: str | None = None

    # WayForPay
    wayforpay_merchant_account: str
    wayforpay_merchant_password: str
    wayforpay_secret_key: str
    wayforpay_domain_name: str
    wayforpay_merchant_domain_name: str
    wayforpay_return_url: str
    wayforpay_service_url: str
    wayforpay_api_url: str
    wayforpay_pay_url: str
    wayforpay_verify_signature: bool
    wayforpay_language: str
    wayforpay_currency: str
    wayforpay_order_prefix: str

    # Конфигурация Pydantic
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # ✅ ВАЖНО: игнорировать дополнительные поля в .env
    )


settings = Settings()
