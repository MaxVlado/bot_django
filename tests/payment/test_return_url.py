# tests/test_return_url.py
import pytest
from django.urls import reverse
from tests.scenario_cov import covers

from core.models import TelegramUser
from subscriptions.models import Plan
from payments.models import Invoice, PaymentStatus


@covers("S16.1")
@pytest.mark.django_db
def test_return_url_without_webhook_shows_pending(client):
    """
    Если вебхук не пришёл (ещё), returnUrl должен вернуть статус 'pending'
    и не менять состояние инвойса.
    """
    user = TelegramUser.objects.create(user_id=777002777, username="ret_pending", first_name="RetPend")
    plan = Plan.objects.create(bot_id=1, name="Plan-30", price=10, currency="UAH", duration_days=30, enabled=True)

    ref = Invoice.generate_order_reference(bot_id=1, user_id=user.user_id, plan_id=plan.id)
    inv = Invoice.objects.create(
        order_reference=ref,
        user=user,
        plan=plan,
        bot_id=1,
        amount=plan.price,
        currency=plan.currency,
        payment_status=PaymentStatus.PENDING,
    )

    # Делаем GET на returnUrl с orderReference (без пришедшего вебхука)
    url = "/api/payments/wayforpay/return/"
    r = client.get(url, {"orderReference": ref})
    assert r.status_code == 200
    data = r.json()

    # Ожидаем, что ответ сигнализирует о "pending"
    assert data.get("status") == "pending"
    assert data.get("payment_status") in (PaymentStatus.PENDING, "PENDING")

    # Инвойс не изменился
    inv.refresh_from_db()
    assert inv.payment_status == PaymentStatus.PENDING
    assert inv.paid_at is None


@covers("S16.1")
@pytest.mark.django_db
def test_return_url_without_ref_returns_error(client):
    """Если нет orderReference, возвращаем понятную ошибку."""
    url = "/api/payments/wayforpay/return/"
    r = client.get(url)  # без параметров
    assert r.status_code == 200  # наша вьюха отвечает 200 с полем error
    data = r.json()
    assert data.get("status") == "error"
    assert "orderReference" in (data.get("message") or data.get("error", ""))
