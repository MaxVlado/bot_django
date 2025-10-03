# bot_runner_aiogram.py
import os
import sys
import asyncio
import logging

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "profiling.settings")
django.setup()

import aiohttp
import asyncpg
from argparse import ArgumentParser

from aiogram import Bot as AioBot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import setup_application, SimpleRequestHandler
from aiohttp import web

from bot.subscriptions import register as register_subs
from bot.config import settings as bot_settings
from core.models import Bot as BotModel
from asgiref.sync import sync_to_async
from leads.bot import register_handlers as register_lead_handlers

# -------------------- logging --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot_runner")


# -------------------- helpers --------------------
async def load_bot_config(bot_id: int):
    # если используешь поле bot_id (а не pk), поменяй фильтр на bot_id=bot_id
    return await sync_to_async(
        BotModel.objects.select_related("merchant_config").get
    )(pk=bot_id)



async def make_pool() -> asyncpg.Pool:
    """
    Создаём пул к той же БД, что и Django, берём параметры из bot/config.py (pydantic settings).
    """
    pool = await asyncpg.create_pool(
        host=bot_settings.db_host,
        port=bot_settings.db_port,
        database=bot_settings.db_name,
        user=bot_settings.db_user,
        password=bot_settings.db_password,
        min_size=1,
        max_size=5,
    )
    return pool


# -------------------- DEV: long-polling --------------------
async def run_longpoll(bot_model: BotModel):
    dp = Dispatcher()

    pool = await make_pool()
    session = aiohttp.ClientSession()

    # регистрируем наши хендлеры меню/подписок
    register_subs(dp, pool=pool, session=session, bot_model=bot_model)

    register_lead_handlers(dp, bot_id=bot_model.bot_id)

    bot = AioBot(
        token=bot_model.token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    logger.info(
        "[DEV] Starting bot bot_id=%s username=@%s in long-polling mode",
        bot_model.bot_id, bot_model.username,
    )

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await session.close()
        await pool.close()


# -------------------- PROD: webhook (aiohttp) --------------------
async def run_webhook(bot_model: BotModel):
    dp = Dispatcher()

    pool = await make_pool()
    session = aiohttp.ClientSession()
    

    # регистрируем наши хендлеры меню/подписок
    register_subs(dp, pool=pool, session=session, bot_model=bot_model)

    register_lead_handlers(dp, bot_id=bot_model.bot_id)

    bot = AioBot(
        token=bot_model.token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    # aiohttp-приложение для входящих апдейтов
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    # Вебхук-путь на домене; в nginx должен быть location /tg/bot-<bot_id>/webhook → proxy_pass http://127.0.0.1:<port>/webhook
    webhook_url = f"https://{bot_model.domain_name}/tg/bot-{bot_model.bot_id}/webhook"

    # поднимаем HTTP-сервер на локальном порту, чтобы nginx мог проксировать
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=bot_model.port)
    await site.start()

    # ставим вебхук (после старта сервера)
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
    )

    # диагностика вебхука
    info = await bot.get_webhook_info()
    logger.info(
        "[WEBHOOK] url=%s pending=%s last_error_date=%s last_error_message=%s ip=%s",
        info.url,
        getattr(info, "pending_update_count", None),
        getattr(info, "last_error_date", None),
        getattr(info, "last_error_message", None),
        getattr(info, "ip_address", None),
    )

    logger.info(
        "[PROD] Bot started: bot_id=%s username=@%s port=%s webhook=%s",
        bot_model.bot_id, bot_model.username, bot_model.port, webhook_url,
    )

    try:
        # держим процесс живым
        while True:
            await asyncio.sleep(3600)
    finally:
        await session.close()
        await pool.close()


# -------------------- entrypoint --------------------
def parse_args():
    p = ArgumentParser()
    p.add_argument("--bot-id", type=int, required=True, help="Bot.bot_id из БД")
    p.add_argument("--dev", action="store_true", help="Запуск в long-poll режиме")
    return p.parse_args()


async def amain():
    parser = ArgumentParser()
    parser.add_argument("--bot-id", type=int, required=True)
    args = parser.parse_args()

    bot_model = await load_bot_config(args.bot_id)   # ← вот здесь эта строка
    await run_webhook(bot_model)

if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except (KeyboardInterrupt, SystemExit):
        pass
