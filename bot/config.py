# bot/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Общие
    bot_id: int
    api_base: str = "http://127.0.0.1:8000/api/payments/wayforpay"

    # БД (одной строкой, а не 5 переменных)
    database_url: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
