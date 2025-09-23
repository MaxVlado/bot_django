# bot/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from collections.abc import Mapping

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅ Назад", callback_data="ui:back")]]
    )



def _rec_get(rec, key, default=None):
    """
    Поддержка dict, asyncpg.Record и прочих Mapping.
    Порядок:
      1) dict.get
      2) Mapping[key] / .get(key)
      3) rec[key] (для asyncpg.Record)
      4) getattr(rec, key, default)
    """
    try:
        if isinstance(rec, dict):
            return rec.get(key, default)

        if isinstance(rec, Mapping):
            # у asyncpg.Record нет .get, но есть __getitem__ и .keys()
            return rec.get(key, default) if hasattr(rec, "get") else (rec[key] if key in rec else default)

        if hasattr(rec, "keys"):  # asyncpg.Record
            if key in rec.keys():
                return rec[key]

        return getattr(rec, key, default)
    except Exception:
        return default


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
