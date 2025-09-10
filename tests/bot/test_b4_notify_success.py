"""
B4.1 — После APPROVED бот отправляет одно подтверждение о продлении/активации.

Ожидание:
- Хендлер/функция notify_payment_success отправляет подтверждение пользователю ОДИН раз.
- Повторный вызов с тем же orderReference НЕ шлёт дубликат (идемпотентно).
- Текст содержит название плана и намёк на активацию/продление, можно дату окончания.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
import bot.main as botmod  # noqa: E402
from bot.main import notify_payment_success  # noqa: E402


class FakeBotAPI:
    """Мок Telegram-бота (aiogram.Bot совместимость по send_message)."""
    def __init__(self):
        self.sent = []  # список (chat_id, text, parse_mode)

    async def send_message(self, chat_id: int, text: str, parse_mode: str | None = None, **kwargs):
        self.sent.append((chat_id, text, parse_mode))


class FakePool:
    """
    Минимальный мок для идемпотентности уведомлений.
    Поддерживает:
      - fetchval(sql, order_reference) -> bool (true, если уже уведомляли)
      - execute(sql, order_reference)  -> помечает как уведомлённого
    """
    def __init__(self):
        self._notified: set[str] = set()

    async def fetchval(self, *_args, **kwargs):
        # ожидаем последний позиционный/именованный аргумент — order_reference
        # поддержим оба варианта вызова
        if kwargs:
            order_ref = kwargs.get("order_reference") or next(iter(kwargs.values()))
        else:
            # последним позиционным параметром обычно идёт order_reference
            order_ref = _args[-1] if _args else None
        return str(order_ref) in self._notified

    async def execute(self, *_args, **kwargs):
        if kwargs:
            order_ref = kwargs.get("order_reference") or next(iter(kwargs.values()))
        else:
            order_ref = _args[-1] if _args else None
        if order_ref is not None:
            self._notified.add(str(order_ref))


@pytest.mark.covers("B4.1")
def test_notify_payment_success_is_idempotent():
    """B4.1: первое уведомление отправляется, повторное — подавляется (идемпотентно)."""
    fake_bot = FakeBotAPI()
    pool = FakePool()

    user_id = 123456
    plan_name = "TEST 8"
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    order_ref = "OR-B4-1-ABC"

    # Первый вызов — должно уйти уведомление
    asyncio.run(
        notify_payment_success(
            pool=pool,
            bot_api=fake_bot,
            user_id=user_id,
            order_reference=order_ref,
            plan_name=plan_name,
            expires_at=expires_at,
        )
    )
    assert len(fake_bot.sent) == 1, "Первый вызов должен отправить подтверждение"
    first_text = fake_bot.sent[0][1]
    assert plan_name in first_text
    assert any(word in first_text.lower() for word in ["продлен", "продлена", "активир", "активирован"])

    # Повторный вызов с тем же orderReference — не должен отправить ещё одно сообщение
    asyncio.run(
        notify_payment_success(
            pool=pool,
            bot_api=fake_bot,
            user_id=user_id,
            order_reference=order_ref,
            plan_name=plan_name,
            expires_at=expires_at,
        )
    )
    assert len(fake_bot.sent) == 1, "Повторный вызов не должен слать дубликат"
