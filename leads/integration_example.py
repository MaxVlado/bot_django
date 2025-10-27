# leads/integration_example.py
"""
ПРИМЕР ИНТЕГРАЦИИ LEAD BOT В bot_runner_aiogram.py

Этот файл показывает, какие изменения нужно внести в bot_runner_aiogram.py
для подключения Lead Bot.
"""

# ============================================================
# ШАГ 1: Добавить импорт в начале файла
# ============================================================

# В начале bot_runner_aiogram.py добавить:
from leads.bot import register_handlers as register_lead_handlers


# ============================================================
# ШАГ 2: Зарегистрировать handlers в run_webhook
# ============================================================

# Найти функцию run_webhook и добавить регистрацию после других handlers:

"""
async def run_webhook(bot_model: BotModel):
    dp = Dispatcher()
    
    pool = await make_pool()
    session = aiohttp.ClientSession()
    
    # Регистрация handlers подписок (УЖЕ ЕСТЬ)
    register_subs(dp, pool=pool, session=session, bot_model=bot_model)
    
    # ✅ ДОБАВИТЬ: Регистрация handlers Lead Bot
    register_lead_handlers(dp, bot_id=bot_model.bot_id)
    
    bot = AioBot(
        token=bot_model.token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    
    # ... остальной код без изменений
"""


# ============================================================
# ШАГ 3: Зарегистрировать handlers в run_longpoll (для DEV)
# ============================================================

# Найти функцию run_longpoll и добавить регистрацию:

"""
async def run_longpoll(bot_model: BotModel):
    dp = Dispatcher()
    
    pool = await make_pool()
    session = aiohttp.ClientSession()
    
    # Регистрация handlers подписок (УЖЕ ЕСТЬ)
    register_subs(dp, pool=pool, session=session, bot_model=bot_model)
    
    # ✅ ДОБАВИТЬ: Регистрация handlers Lead Bot
    register_lead_handlers(dp, bot_id=bot_model.bot_id)
    
    bot = AioBot(
        token=bot_model.token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    
    # ... остальной код без изменений
"""


# ============================================================
# ПОЛНЫЙ ПРИМЕР ФУНКЦИИ run_webhook С ИНТЕГРАЦИЕЙ
# ============================================================

"""
async def run_webhook(bot_model: BotModel):
    dp = Dispatcher()

    pool = await make_pool()
    session = aiohttp.ClientSession()

    # Регистрация handlers для подписок
    register_subs(dp, pool=pool, session=session, bot_model=bot_model)
    
    # ✅ Регистрация handlers для Lead Bot
    register_lead_handlers(dp, bot_id=bot_model.bot_id)

    bot = AioBot(
        token=bot_model.token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    # aiohttp-приложение для входящих апдейтов
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    webhook_url = f"https://{bot_model.domain_name}/tg/bot-{bot_model.bot_id}/webhook"

    # поднимаем HTTP-сервер на локальном порту
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=bot_model.port)
    await site.start()

    # ставим вебхук
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
"""


# ============================================================
# ПРИМЕЧАНИЯ
# ============================================================

"""
1. Lead Bot использует FSM (Finite State Machine) для управления состояниями
   диалога с пользователем. Это не конфликтует с другими handlers.

2. Lead Bot регистрирует свои handlers через Router, который затем 
   включается в основной Dispatcher.

3. Все handlers Lead Bot работают с префиксами:
   - Команды: /start, /cancel
   - Callback data: phone:*, comment:*, confirm:*,

4. FSM состояния хранятся в памяти (или Redis, если настроен storage).

5. Bot ID передается через middleware во все handlers для правильной
   привязки к конфигурации.

6. Рекомендуется запускать бота в режиме webhook (production) или
   longpoll (development).
"""


# ============================================================
# ПРОВЕРКА ИНТЕГРАЦИИ
# ============================================================

print("""
ПРОВЕРКА ИНТЕГРАЦИИ:

1. Убедитесь что импорт добавлен:
   from leads.bot import register_handlers as register_lead_handlers

2. Убедитесь что регистрация добавлена в обе функции:
   register_lead_handlers(dp, bot_id=bot_model.bot_id)

3. Запустите бота:
   python bot_runner_aiogram.py --bot-id <BOT_ID>

4. Проверьте логи:
   - Должны быть сообщения от leads.bot
   - Не должно быть ошибок импорта

5. Протестируйте бота:
   - Отправьте /start
   - Пройдите весь процесс заполнения
   - Проверьте сохранение в БД
   - Проверьте уведомления (email/telegram)

УСПЕШНАЯ ИНТЕГРАЦИЯ = бот отвечает на /start и ведет диалог.
""")
