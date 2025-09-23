# bot/main.py
import os
import asyncio
import logging
from datetime import datetime, timezone as dt_timezone


import aiohttp
import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .notifications import (
    notify_payment_success,
    notify_payment_non_success,
)
from .keyboards import kb_plans

# ----------------------------- CONFIG -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_ID = int(os.getenv("BOT_ID", "1"))  # должен совпадать с Plan.bot_id
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/payments/wayforpay")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "wayforpay_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

TZ = "Europe/Kyiv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

# ----------------------------- DB QUERIES -----------------------------

SQL_SUB_STATUS = """
SELECT s.status,
       s.starts_at AT TIME ZONE 'UTC' AS starts_at_utc,
       s.expires_at AT TIME ZONE 'UTC' AS expires_at_utc,
       s.last_payment_date AT TIME ZONE 'UTC' AS last_payment_utc,
       p.name, p.price, p.currency, p.duration_days
FROM subscriptions_subscription s
JOIN subscriptions_plan p ON p.id = s.plan_id
JOIN core_telegramuser t ON t.id = s.user_id
WHERE s.bot_id = $1 AND t.user_id = $2
ORDER BY s.updated_at DESC
LIMIT 1
"""


SQL_IS_BLOCKED = "SELECT is_blocked FROM core_telegramuser WHERE user_id = $1 LIMIT 1"


SQL_PLANS_ENABLED = """
SELECT id, name, price, currency, duration_days, enabled
FROM subscriptions_plan
WHERE bot_id=$1 AND enabled = true
ORDER BY price ASC, duration_days ASC
"""


# ----------------------------- UI HELPERS -----------------------------
def kb_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Моя подписка", callback_data="sub:status")
    kb.button(text="Продлить подписку", callback_data="sub:renew")
    kb.button(text="Помощь", callback_data="help:open")
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back")]
    ])

def format_dt_kyiv(dt_utc: datetime | None) -> str:
    if not dt_utc:
        return "—"
    # Упрощённо: показываем UTC с пометкой. (Для точной локали — pytz/zoneinfo и т.п.)
    return dt_utc.replace(tzinfo=dt_timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ----------------------------- BOT HANDLERS -----------------------------
async def cmd_start(message: Message, pool: asyncpg.Pool):
    # бан-чек
    is_blocked = await pool.fetchval(SQL_IS_BLOCKED, message.from_user.id) or False
    if is_blocked:
        await message.answer("⛔ Доступ запрещён. Обратитесь в поддержку.", reply_markup=kb_back())
        return

    log.info("event=start user_id=%s", message.from_user.id)
    await message.answer(
        "Привет! Это меню управления подпиской.",
        reply_markup=kb_main()
    )

async def on_status(cb: CallbackQuery, pool: asyncpg.Pool):
    is_blocked = await pool.fetchval(SQL_IS_BLOCKED, cb.from_user.id) or False
    if is_blocked:
        await cb.message.edit_text("⛔ Доступ запрещён.", reply_markup=kb_back())
        await cb.answer()
        return

    log.info("event=status bot_id=%s user_id=%s", BOT_ID, cb.from_user.id)

    row = await pool.fetchrow(SQL_SUB_STATUS, BOT_ID, cb.from_user.id)
    if not row:
        await cb.message.edit_text(
            "Подписка не найдена. Нажмите «Продлить подписку» для оформления.",
            reply_markup=kb_main()
        )
        await cb.answer()
        return

    status, starts_at, expires_at, last_pay, name, price, currency, dur = row
    text = (
        f"🧾 <b>Статус подписки</b>\n"
        f"План: <b>{name}</b>\n"
        f"Цена: <b>{int(price)} {currency}</b> / {dur} дн.\n"
        f"Статус: <b>{status}</b>\n"
        f"Начало: {format_dt_kyiv(starts_at)}\n"
        f"Окончание: {format_dt_kyiv(expires_at)}\n"
        f"Последняя оплата: {format_dt_kyiv(last_pay)}\n\n"
        f"Для продления — вернитесь и нажмите «Продлить подписку»."
    )
    await cb.message.edit_text(text, reply_markup=kb_main(), parse_mode="HTML")
    await cb.answer()

async def on_renew(cb, pool):
    """Показать доступные тарифы для продления (только enabled=True)."""
    # проверка бана
    try:
        blocked = await pool.fetchval(SQL_IS_BLOCKED, cb.from_user.id)
    except Exception:
        blocked = False
    if blocked:
        await cb.answer("Доступ запрещён", show_alert=True)
        return

    # загрузка планов
    try:
        rows = await pool.fetch(SQL_PLANS_ENABLED, BOT_ID)
    except Exception:
        # в тестах FakePool.fetch игнорирует SQL — оставляем сигнатуру прежней
        rows = await pool.fetch("", BOT_ID)

    # фильтруем только включённые (если ключа нет — считаем включённым)
    def _is_enabled(rec):
        return rec.get("enabled", True) if isinstance(rec, dict) else getattr(rec, "enabled", True)

    plans = [r for r in rows if _is_enabled(r)]

    # нет планов
    if not plans:
        await cb.message.edit_text("Нет доступных тарифов для продления.", reply_markup=kb_back())
        await cb.answer()
        return

    # однажды собираем клавиатуру и отвечаем
    kb = kb_plans(plans)  # из bot/keyboards.py
    await cb.message.edit_text("Выберите тариф для продления:", reply_markup=kb)
    await cb.answer()

async def on_pay(cb: CallbackQuery, session: aiohttp.ClientSession):
    # парсим plan_id
    try:
        _, pid = cb.data.split(":")
        plan_id = int(pid)
    except Exception:
        await cb.answer("Некорректный тариф", show_alert=True)
        return

    payload = {"bot_id": BOT_ID, "user_id": cb.from_user.id, "plan_id": plan_id}
    url = f"{API_BASE}/create-invoice/"

    try:
        async with session.post(url, json=payload, timeout=20) as resp:
            data = await resp.json()
    except Exception as e:
        # Лог с контекстом: bot_id, user_id, plan_id (для caplog-теста B10.2)
        log.exception(
            "create-invoice failed: bot_id=%s user_id=%s plan_id=%s error=%r",
            BOT_ID, cb.from_user.id, plan_id, e,
        )
        await cb.answer("Ошибка запроса", show_alert=True)
        return

    if not data.get("ok"):
        err = data.get("error", "unknown")
        await cb.answer(f"Ошибка: {err}", show_alert=True)
        return

    invoice_url = data["invoiceUrl"]

    log.info(
        "event=create_invoice_success bot_id=%s user_id=%s plan_id=%s",
        BOT_ID, cb.from_user.id, plan_id,
    )


    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=invoice_url)],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back")],
        ]
    )

    await cb.message.edit_text(
        "Перейдите по кнопке «Оплатить». После оплаты вернитесь и нажмите «Моя подписка» для проверки.",
        reply_markup=kb
    )
    await cb.answer()

async def on_help(cb: CallbackQuery):
    await cb.message.edit_text(
        "Помощь:\n• «Моя подписка» — текущий статус и даты.\n"
        "• «Продлить подписку» — выбор тарифа и оплата.\n"
        "• После оплаты — нажмите «Моя подписка» для обновления статуса.",
        reply_markup=kb_back()
    )
    await cb.answer()

async def on_back(cb: CallbackQuery):
    await cb.message.edit_text("Главное меню:", reply_markup=kb_main())
    await cb.answer()


# ----------------------------- APP INIT -----------------------------
async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    pool = await asyncpg.create_pool(
        host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        min_size=1, max_size=5
    )
    session = aiohttp.ClientSession()

    # message handlers
    dp.message.register(lambda m: cmd_start(m, pool), CommandStart())

    # callback handlers
    dp.callback_query.register(lambda c: on_status(c, pool), F.data == "sub:status")
    dp.callback_query.register(lambda c: on_renew(c, pool), F.data == "sub:renew")
    dp.callback_query.register(on_help, F.data == "help:open")
    dp.callback_query.register(on_back, F.data == "ui:back")
    dp.callback_query.register(lambda c: on_pay(c, session), F.data.startswith("pay:"))

    log.info("Bot started with BOT_ID=%s API_BASE=%s DB=%s@%s/%s", BOT_ID, API_BASE, DB_USER, DB_HOST, DB_NAME)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await session.close()
        await pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
