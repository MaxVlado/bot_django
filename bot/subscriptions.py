# bot/subscriptions.py
import os
import logging
from datetime import datetime, timezone as dt_timezone
from functools import partial

from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards import kb_plans, kb_back, kb_main_menu

log = logging.getLogger("bot.subscriptions")

# --- CONFIG (совместимо с bot/main.py) ---
BOT_ID = int(os.getenv("BOT_ID", "1"))
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/payments/wayforpay")

# --- SQL (взято из bot/main.py) ---
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

def format_dt_kyiv(dt_utc: datetime | None) -> str:
    if not dt_utc:
        return "—"
    return dt_utc.replace(tzinfo=dt_timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# --- HANDLERS ---
async def cmd_start(message: types.Message, pool):
    is_blocked = await pool.fetchval(SQL_IS_BLOCKED, message.from_user.id) or False
    if is_blocked:
        await message.answer("⛔ Доступ запрещён.", reply_markup=kb_back())
        return

    await message.answer(
        "Привет! Это меню управления подпиской.",
        reply_markup=kb_main_menu()
    )

async def on_status(cb: types.CallbackQuery, pool):
    is_blocked = await pool.fetchval(SQL_IS_BLOCKED, cb.from_user.id) or False
    if is_blocked:
        await cb.message.edit_text("⛔ Доступ запрещён.", reply_markup=kb_back())
        await cb.answer(); return

    row = await pool.fetchrow(SQL_SUB_STATUS, BOT_ID, cb.from_user.id)
    if not row:
        await cb.message.edit_text(
            "Подписка не найдена. Нажмите «Продлить подписку» для оформления.",
            reply_markup=kb_main_menu()
        )
        await cb.answer(); return

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
    await cb.message.edit_text(text, reply_markup=kb_main_menu(), parse_mode="HTML")
    await cb.answer()

async def on_renew(cb: types.CallbackQuery, pool):
    blocked = await pool.fetchval(SQL_IS_BLOCKED, cb.from_user.id) or False
    if blocked:
        await cb.answer("Доступ запрещён", show_alert=True); return

    rows = await pool.fetch(SQL_PLANS_ENABLED, BOT_ID)
    plans = [r for r in rows if (r.get("enabled", True) if isinstance(r, dict) else getattr(r, "enabled", True))]
    if not plans:
        await cb.message.edit_text("Нет доступных тарифов.", reply_markup=kb_back())
        await cb.answer(); return

    kb = kb_plans(plans)
    await cb.message.edit_text("Выберите тариф для продления:", reply_markup=kb)
    await cb.answer()

async def on_pay(cb: types.CallbackQuery, session):
    try:
        _, pid = cb.data.split(":")
        plan_id = int(pid)
    except Exception:
        await cb.answer("Некорректный тариф", show_alert=True); return

    payload = {"bot_id": BOT_ID, "user_id": cb.from_user.id, "plan_id": plan_id}
    url = f"{API_BASE}/create-invoice/"

    try:
        async with session.post(url, json=payload, timeout=20) as resp:
            data = await resp.json()
    except Exception as e:
        log.exception("create-invoice failed: bot_id=%s user_id=%s plan_id=%s error=%r",
                      BOT_ID, cb.from_user.id, plan_id, e)
        await cb.answer("Ошибка запроса", show_alert=True); return

    if not data.get("ok"):
        await cb.answer(f"Ошибка: {data.get('error','unknown')}", show_alert=True); return

    invoice_url = data["invoiceUrl"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=invoice_url)],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back")],
    ])
    await cb.message.edit_text(
        "Перейдите по кнопке «Оплатить». После оплаты вернитесь и нажмите «Моя подписка».",
        reply_markup=kb
    )
    await cb.answer()

async def on_help(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Помощь:\n• «Моя подписка» — текущий статус и даты.\n"
        "• «Продлить подписку» — выбор тарифа и оплата.\n"
        "• После оплаты — нажмите «Моя подписка» для обновления статуса.",
        reply_markup=kb_back()
    )
    await cb.answer()

async def on_back(cb: types.CallbackQuery):
    await cb.message.edit_text("Главное меню:", reply_markup=kb_main_menu())
    await cb.answer()

def register(dp, *, pool, session):
    # /start
    dp.message.register(partial(cmd_start, pool=pool), Command("start"))
    # callbacks
    dp.callback_query.register(partial(on_status, pool=pool), lambda c: c.data == "sub:status")
    dp.callback_query.register(partial(on_renew,  pool=pool), lambda c: c.data == "sub:renew")
    dp.callback_query.register(on_help,  lambda c: c.data == "help:open")
    dp.callback_query.register(on_back,  lambda c: c.data == "ui:back")
    dp.callback_query.register(partial(on_pay, session=session), lambda c: c.data and c.data.startswith("pay:"))
