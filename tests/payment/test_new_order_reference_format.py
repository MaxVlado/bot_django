# tests/payment/test_new_order_reference_format.py
import json
import pytest
from datetime import timedelta
from django.utils import timezone

from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from payments.models import Invoice, PaymentStatus
from payments.wayforpay.api import WayForPayAPI


class TestNewOrderReferenceFormat:
    """Тесты для нового формата ORDER_timestamp+rand_user_plan"""
    
    @pytest.fixture
    def api(self):
        return WayForPayAPI()
    
    def test_generate_order_reference_format(self):
        """Проверяем что генерация создаёт правильный формат"""
        ref = Invoice.generate_order_reference(bot_id=1, user_id=407673079, plan_id=2)
        
        # Проверяем структуру
        assert ref.startswith("ORDER_")
        
        parts = ref[6:].split('_')  # убираем ORDER_ и делим
        assert len(parts) == 3
        
        # parts[0] должно быть timestamp + 3 символа
        assert len(parts[0]) >= 10  # минимум 10 цифр timestamp
        
        # parts[1] = user_id
        assert parts[1] == "407673079"
        
        # parts[2] = plan_id
        assert parts[2] == "2"
        
        print(f"✅ Generated: {ref}")
    
    def test_parse_order_reference(self, api):
        """Тест парсинга формата ORDER_1758606042kjI_407673079_2"""
        ref = "ORDER_1758606042kjI_407673079_2"
        
        user_id, plan_id, timestamp = api.parse_order_reference(ref)
        
        assert user_id == 407673079
        assert plan_id == 2
        assert timestamp == 1758606042
        
        print(f"✅ Parsed: user_id={user_id}, plan_id={plan_id}, ts={timestamp}")
    
    def test_parse_with_semicolon(self, api):
        """Парсинг с точкой с запятой в конце"""
        ref = "ORDER_1758606042kjI_407673079_2;"
        
        user_id, plan_id, timestamp = api.parse_order_reference(ref)
        
        assert user_id == 407673079
        assert plan_id == 2
    
    def test_parse_invalid_format_raises_error(self, api):
        """Неверный формат должен вызывать ошибку"""
        
        with pytest.raises(ValueError, match="must start with ORDER_"):
            api.parse_order_reference("WRONG_123_456_789")
        
        with pytest.raises(ValueError, match="expected 3 parts"):
            api.parse_order_reference("ORDER_123_456")  # только 2 части
    
    @pytest.mark.django_db
    def test_create_invoice_with_new_format(self):
        """Проверяем создание Invoice с новым форматом"""
        user = TelegramUser.objects.create(
            user_id=407673079,
            username="test"
        )
        
        plan = Plan.objects.create(
            bot_id=1,
            name="Test Plan",
            price=100,
            currency="UAH",
            duration_days=30,
            enabled=True
        )
        
        # Генерируем orderReference
        ref = Invoice.generate_order_reference(
            bot_id=1,
            user_id=user.user_id,
            plan_id=plan.id
        )
        
        # Создаём Invoice
        inv = Invoice.objects.create(
            order_reference=ref,
            user=user,
            plan=plan,
            bot_id=1,
            amount=100,
            currency="UAH",
            payment_status=PaymentStatus.PENDING
        )
        
        # Проверяем что сохранилось
        assert inv.order_reference.startswith("ORDER_")
        assert f"_{user.user_id}_" in inv.order_reference
        assert inv.order_reference.endswith(f"_{plan.id}")
        
        print(f"✅ Created Invoice: {inv.order_reference}")
    
    @pytest.mark.django_db
    def test_webhook_with_new_format(self, client, settings):
        """E2E тест: webhook с новым форматом"""
        # Отключаем проверку подписи для теста
        settings.WAYFORPAY_VERIFY_SIGNATURE = False
        
        user = TelegramUser.objects.create(
            user_id=407673079,
            username="realuser"
        )
        
        plan = Plan.objects.create(
            bot_id=1,
            name="Месячная подписка",
            price=2,
            currency="UAH",
            duration_days=30,
            enabled=True
        )
        
        # ИСПРАВЛЕНО: используем реальный plan.id
        ref = f"ORDER_1758606042kjI_{user.user_id}_{plan.id}"
        inv = Invoice.objects.create(
            order_reference=ref,
            user=user,
            plan=plan,
            bot_id=1,
            amount=2,
            currency="UAH",
            payment_status=PaymentStatus.PENDING
        )
        
        # Реальный payload - также обновляем orderReference
        payload = {
            "merchantAccount": "profiling_club",
            "orderReference": f"{ref};",  # WayForPay добавляет ; в конце
            "amount": 2,
            "currency": "UAH",
            "authCode": "629283",
            "email": "netdesopgame@gmail.com",
            "phone": "380645454545",
            "cardPan": "44****6868",
            "cardType": "Visa",
            "issuerBankCountry": "Ukraine",
            "issuerBankName": "JSC UNIVERSAL BANK",
            "transactionStatus": "Approved",
            "reasonCode": 1100,
            "fee": 0.04,
            "paymentSystem": "card",
            "rrn": "514215155299"
        }
        
        # Отправляем
        response = client.post(
            "/api/payments/wayforpay/webhook/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        
        # Проверяем
        assert response.status_code == 200
        
        inv.refresh_from_db()
        assert inv.payment_status == PaymentStatus.APPROVED
        assert inv.email == "netdesopgame@gmail.com"
        assert inv.card_pan == "44****6868"
        assert inv.paid_at is not None
        
        # Проверяем подписку
        sub = Subscription.objects.get(user=user, bot_id=1)
        assert sub.status == SubscriptionStatus.ACTIVE
        
        now = timezone.now()
        expected = now + timedelta(days=30)
        assert (expected - timedelta(hours=1)) <= sub.expires_at <= (expected + timedelta(hours=1))
        
        print("✅ Webhook обработан успешно!")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])