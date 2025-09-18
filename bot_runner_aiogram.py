import sys
import os
import django
import asyncio
import logging
import asyncpg
import aiohttp

from aiogram import Bot as AioBot, Dispatcher
from aiogram.webhook.aiohttp_server import setup_application, SimpleRequestHandler
from aiohttp import web
from aiogram.client.default import DefaultBotProperties

from bot.subscriptions import register as register_subs
from bot.config import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "profiling.settings")
django.setup()

from core.models import Bot as BotModel


# --- logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def load_bot_config(bot_id: int):
    bot = BotModel.objects.get(pk=bot_id)
    merchant = getattr(bot, "merchant_config", None)
    return bot, merchant


async def run_webhook(bot_model: BotModel):
    """Prod режим: webhook через aiohttp"""
    dp = Dispatcher()

    pool = await asyncpg.create_pool(dsn=settings.database_url)
    session = aiohttp.ClientSession()

    register_subs(dp, pool=pool, session=session)

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

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await session.close()
        await pool.close()
