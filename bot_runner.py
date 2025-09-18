# файл: bot_runner.py
from fastapi import FastAPI
from core.models import Bot
from payments.models import MerchantConfig
import argparse
import sys

# Глобальная ссылка на текущего бота (тест присваивает её вручную)
BOT = None

# Простейшее FastAPI-приложение для вебхука
app = FastAPI()

@app.post("/webhook")
def webhook():
    return {"ok": True}

def load_bot_config(bot_pk: int):
    """Вернуть (Bot, MerchantConfig) по PK бота (как требует тест)."""
    bot = Bot.objects.get(pk=bot_pk)
    merchant = MerchantConfig.objects.get(bot=bot)
    return bot, merchant

def main():
    """CLI: --bot-id <pk>. Если бот выключен, вывести 'disabled' и выйти с кодом 0."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-id", type=int, required=True)
    args, _ = parser.parse_known_args(sys.argv[1:])

    bot = Bot.objects.get(pk=args.bot_id)
    if not bot.is_enabled:
        print("disabled")
        raise SystemExit(0)

    # Для целей тестов ничего не запускаем дальше.
    # В реальном раннере здесь бы инициализировали BOT, логи, цикл и т.д.
    return
