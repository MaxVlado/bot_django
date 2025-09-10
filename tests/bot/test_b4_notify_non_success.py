"""
B4.3 — Неуспешные/промежуточные статусы: бот НЕ шлёт 'успех', допустимо информативное сообщение.

Ожидание:
- Функция notify_payment_non_success отправляет информативное сообщение пользователю.
- Сообщение не содержит шаблона удачной оплаты ("Платёж подтверждён").
- Отрабатывает для статусов: DECLINED, REFUNDED, EXPIRED, PENDING, IN_PROCESS, WAITING_AUTH_COMPLETE.
"""
import asyncio
import pytest

aiogram = pytest.importorskip("aiogram")  # noqa: F401
from bot.main import notify_payment_non_success  # noqa: E402


class FakeBotAPI:
    """Мок Telegram API — совместим с aiogram.Bot по send_message."""
    def __init__(self):
        self.sent = []  # список (chat_id, text, parse_mode)

    async def send_message(self, chat_id: int, text: str, parse_mode: str | None = None, **kwargs):
        self.sent.append((chat_id, text, parse_mode))


@pytest.mark.covers("B4.3")
@pytest.mark.parametrize("status", [
    "DECLINED", "REFUNDED", "EXPIRED", "PENDING", "IN_PROCESS", "WAITING_AUTH_COMPLETE",
])
def test_notify_non_success_does_not_claim_success(status):
    """B4.3: Для неуспешных и промежуточных статусов не должно быть сообщения об успехе."""
    fake_bot = FakeBotAPI()

    asyncio.run(
        notify_payment_non_success(
            bot_api=fake_bot,
            user_id=123456,
            order_reference=f"OR-{status}",
            status=status,
            reason="test-reason",
        )
    )

    # Должно уйти 1 информативное сообщение
    assert len(fake_bot.sent) == 1, "Ожидается ровно одно информативное сообщение"
    text = fake_bot.sent[0][1]
    # Не должно содержать шаблон успеха
    assert "Платёж подтверждён" not in text
    # Должно упоминать статус или причину
    lowered = text.lower()
    assert any(key in lowered for key in [
        "declin", "refund", "возврат", "expired", "истек", "pending", "ожид", "process", "3ds", "auth"
    ]) or "test-reason" in lowered, "Сообщение должно быть информативным по статусу/причине"
