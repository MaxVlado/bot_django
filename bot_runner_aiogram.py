import sys
import os
import django
import asyncio
import logging

from aiogram import Bot as AioBot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import setup_application, SimpleRequestHandler
from aiohttp import web
from aiogram.client.default import DefaultBotProperties

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "profiling.settings")
django.setup()

from core.models import Bot as BotModel
from payments.models import MerchantConfig

# --- basic logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def start_handler(message: Message):
    await message.answer("✅ Бот запущен и готов к работе!")


def load_bot_config(bot_id: int):
    bot = BotModel.objects.get(pk=bot_id)
    merchant = getattr(bot, "merchant_config", None)
    return bot, merchant


async def run_longpoll(bot_model: BotModel):
    """Dev режим: long-polling"""
    dp = Dispatcher()
    dp.message.register(start_handler, Command("start"))

    bot = AioBot(
        token=bot_model.token,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    logger.info(f"[DEV] Starting bot {bot_model.id} @{bot_model.username} in long-polling mode")
    await dp.start_polling(bot)


async def run_webhook(bot_model: BotModel):
    """Prod режим: webhook через aiohttp"""
    dp = Dispatcher()
    dp.message.register(start_handler, Command("start"))

    bot = AioBot(
        token=bot_model.token,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    webhook_url = f"https://{bot_model.domain_name}/tg/bot-{bot_model.id}/webhook"
    await bot.set_webhook(webhook_url)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", bot_model.port)
    logger.info(
        f"[PROD] Starting bot {bot_model.id} @{bot_model.username} "
        f"on port {bot_model.port}, webhook={webhook_url}"
    )
    await site.start()

    # Блокировка
    while True:
        await asyncio.sleep(3600)


def main():
    if "--bot-id" not in sys.argv:
        print("Usage: bot_runner_aiogram.py --bot-id <id> [--dev]")
        sys.exit(1)

    bot_id = int(sys.argv[sys.argv.index("--bot-id") + 1])
    bot_model, merchant = load_bot_config(bot_id)

    if not bot_model.is_enabled:
        print(f"Bot {bot_id} is disabled.")
        sys.exit(0)

    dev_mode = "--dev" in sys.argv

    try:
        if dev_mode:
            asyncio.run(run_longpoll(bot_model))
        else:
            asyncio.run(run_webhook(bot_model))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
