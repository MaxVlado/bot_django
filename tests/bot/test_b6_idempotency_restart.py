"""
B6.1 — Два одинаковых APPROVED (повторная доставка/после рестарта процесса):
одно уведомление пользователю — повторное подавляется благодаря записи в БД.
"""
import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.notifications import notify_payment_success  # noqa: E402


class FakeBotAPI:
    """Мок Telegram Bot API (совместим по send_message)."""
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id: int, text: str, parse_mode: str | None = None, **kwargs):
        self.sent.append((chat_id, text, parse_mode))


class FakePoolPreNotified:
    """
    Имитация «после рестарта»: в БД уже есть запись, что по этому order_reference уведомление отправлено.
    - fetchval(...) -> True (уже уведомляли)
    - execute(...)  -> no-op
    """
    def __init__(self, pre_marked_refs: set[str]):
        self._marked = set(pre_marked_refs)

    async def fetchval(self, *_args, **kwargs):
        # в notify_payment_success первым аргументом после SQL идёт order_reference
        order_ref = kwargs.get("order_reference")
        if order_ref is None and _args:
            order_ref = _args[-1]
        return str(order_ref) in self._marked

    async def execute(self, *_args, **kwargs):
        # no-op: считаем, что запись уже есть
        return


@pytest.mark.covers("B6.1")
def test_idempotency_after_restart_no_duplicate():
    """B6.1: Если запись об отправке уже есть (рестарт процесса), сообщение не дублируется."""
    bot = FakeBotAPI()
    order_ref = "OR-RESTART-123"
    pool = FakePoolPreNotified({order_ref})  # уже «помечено» в БД

    # Пытаемся «повторно» отправить подтверждение
    sent_now = asyncio.run(
        notify_payment_success(
            pool=pool,
            bot_api=bot,
            user_id=1010,
            order_reference=order_ref,
            plan_name="TEST 8",
            expires_at=None,
        )
    )

    assert sent_now is False, "Функция должна вернуть False, если уже уведомляли ранее"
    assert len(bot.sent) == 0, "Сообщение не должно отправляться повторно"
