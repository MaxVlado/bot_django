# bot/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back")]]
    )

def _rec_get(rec, key, default=None):
    return rec.get(key, default) if isinstance(rec, dict) else getattr(rec, key, default)

def _rec_enabled(rec) -> bool:
    # Если ключа нет — считаем включённым (совместимость с тестами/моками)
    return _rec_get(rec, "enabled", True) is not False

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧾 Моя подписка", callback_data="sub:status")],
            [InlineKeyboardButton(text="🔁 Продлить подписку", callback_data="sub:renew")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help:open")],
        ]
    )

def kb_plans(plans) -> InlineKeyboardMarkup:
    rows = []
    for rec in plans:
        if not _rec_enabled(rec):
            continue
        pid = _rec_get(rec, "id")
        name = _rec_get(rec, "name", "")
        price = _rec_get(rec, "price", "")
        curr = _rec_get(rec, "currency", "UAH")
        dur = _rec_get(rec, "duration_days", "")
        label = f"{name} — {price} {curr} / {dur} дней"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"pay:{pid}")])
    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
