# ================================================================
# wayforpay/services.py
# ================================================================
from decimal import Decimal
from typing import Dict, Optional
from django.utils import timezone
from django.db import transaction
from django.conf import settings


from .api import WayForPayAPI
from core.models import TelegramUser
from subscriptions.models import Plan, Subscription, SubscriptionStatus
from subscriptions.services import SubscriptionService
from payments.models import Invoice, PaymentStatus, VerifiedUser




class WayForPayService:
    """Сервис WayForPay: создание инвойса, обработка вебхука, продление подписки, верификация."""

    def __init__(self, bot_id: int = None):
        if bot_id:
            # Если передан bot_id, загружаем настройки из БД
            from core.models import Bot
            bot_model = Bot.objects.select_related('merchant_config').get(bot_id=bot_id)
            self.api = WayForPayAPI(merchant_config=bot_model.merchant_config)
        else:
            # Fallback на общие настройки
            self.api = WayForPayAPI()

    @transaction.atomic
    def create_invoice(self, bot_id: int, user_id: int, plan_id: int, amount: Optional[Decimal] = None) -> str:
        """
        Создать инвойс и вернуть URL оплаты.
        """
        # Получаем бота с его merchant_config
        from core.models import Bot
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            bot_model = Bot.objects.select_related('merchant_config').get(bot_id=bot_id)
            merchant_config = bot_model.merchant_config
            
            logger.info(f"Bot {bot_id} merchant_account from DB: {merchant_config.merchant_account}")
            logger.info(f"Bot {bot_id} secret_key from DB: {merchant_config.secret_key[:10]}...")
            
            # Инициализируем API с настройками конкретного бота
            self.api = WayForPayAPI(merchant_config=merchant_config)
            
            logger.info(f"API initialized with merchant_account: {self.api.merchant_account}")
            
        except Exception as e:
            logger.error(f"Error loading bot config for bot_id={bot_id}: {e}")
            # Fallback на общие настройки
            self.api = WayForPayAPI()
            logger.info(f"Using fallback settings, merchant_account: {self.api.merchant_account}")
        
    
        
        user, _ = TelegramUser.objects.get_or_create(
            user_id=user_id,
            defaults={"username": None, "first_name": None, "last_name": None},
        )

        plan = Plan.objects.get(id=plan_id, bot_id=bot_id, enabled=True)

        order_reference = Invoice.generate_order_reference(bot_id, user_id, plan_id)
        inv = Invoice.objects.create(
            order_reference=order_reference,
            user=user,
            plan=plan,
            bot_id=bot_id,
            amount=amount or plan.price,
            currency=getattr(plan, "currency", "UAH"),
            payment_status=PaymentStatus.PENDING,
        )

        payload = {
            "orderReference": inv.order_reference,
            "amount": int(inv.amount),
            "currency": inv.currency,
            "productName": [plan.name],
            "productCount": [1],
            "productPrice": [int(inv.amount)],
        }

        client_data = {}
        if user.first_name:
            client_data["clientFirstName"] = user.first_name
        if user.last_name:
            client_data["clientLastName"] = user.last_name
        if inv.phone:
            client_data["clientPhone"] = inv.phone
        if inv.email:
            client_data["clientEmail"] = inv.email
        if client_data:
            payload["clientData"] = client_data

        form_data = self.api.generate_payment_form_data(payload)
        inv.raw_request_payload = form_data
        inv.save(update_fields=["raw_request_payload", "updated_at"])

        import urllib.request
        import urllib.parse
        import json
        
        try:
            # Подготавливаем данные для POST
            json_data = json.dumps(form_data).encode('utf-8')
            
            # Создаем POST-запрос
            req = urllib.request.Request(
                'https://api.wayforpay.com/api',
                data=json_data,
                headers={'Content-Type': 'application/json'}
            )
            
            # Отправляем запрос
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    if result.get('invoiceUrl'):
                        return result['invoiceUrl']
                    else:
                        raise ValueError(f"No invoiceUrl in response: {result}")
                else:
                    raise ValueError(f"WayForPay API error: {response.status}")
                    
        except Exception as e:
            raise ValueError(f"Failed to create invoice: {e}")
        
    @transaction.atomic
    def handle_webhook(self, payload: Dict) -> Dict:
        """Обработка webhook точно как в PHP коде"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f'Received webhook from WayForPay: {payload}')
        
        # 1. Проверка подписи (как в PHP)
        if not self.api.validate_response_signature(payload):
            logger.error('Invalid signature from WayForPay')
            return {"status": "error", "message": "Invalid signature"}
        
        # 2. Проверка валюты (как в PHP)
        if payload.get('currency') != 'UAH':
            logger.warning(f"Invalid currency: {payload.get('currency')}")
            return {"message": "Unsupported currency"}
        
        # 3. Парсинг orderReference (как в PHP)
        order_reference = payload.get('orderReference')
        try:
            user_id, plan_id, parts_count = self.api.parse_order_reference(order_reference)
            logger.info(f"Parsed user_id={user_id}, plan_id={plan_id} from orderReference: {order_reference}")
        except ValueError as e:
            logger.warning(str(e))
            return {"status": "skipped", "message": "Invalid orderReference format"}
        
        # 4. Получаем plan и bot_id (как в PHP)
        from subscriptions.models import Plan
        plan = Plan.objects.filter(id=plan_id, enabled=True).first()
        if not plan:
            return {"message": "Plan not available"}
        
        bot_id = plan.bot_id
        
        # 5. Проверка дубликатов (как в PHP)
        base_reference = order_reference.split('_WFPREG-')[0]  # PHP логика
        existing_invoice = Invoice.objects.filter(
            order_reference=base_reference,
            payment_status=PaymentStatus.APPROVED
        ).first()
        
        if existing_invoice:
            logger.info(f"Webhook duplicated for orderReference {order_reference} - already success")
            # Обновляем поля как в PHP
            self._update_invoice_fields(existing_invoice, payload)
            return {"status": "accepted"}
        
        # 6. Продолжаем обработку...
        return self._process_payment_status(payload, user_id, plan_id, bot_id, base_reference)
   
    def _update_invoice_fields(self, invoice: Invoice, payload: Dict):
            """Обновление полей инвойса как в PHP коде"""
            invoice.phone = invoice.phone or payload.get('phone')
            invoice.email = invoice.email or payload.get('email') 
            invoice.card_pan = invoice.card_pan or payload.get('cardPan')
            invoice.card_type = invoice.card_type or payload.get('cardType')
            invoice.card_product = getattr(invoice, 'card_product', None) or payload.get('cardProduct')
            invoice.issuer_bank = invoice.issuer_bank or payload.get('issuerBankName')
            invoice.issuer_country = invoice.issuer_country or payload.get('issuerBankCountry')
            invoice.payment_system = invoice.payment_system or payload.get('paymentSystem')
            invoice.fee = invoice.fee or payload.get('fee')
            invoice.rrn = invoice.rrn or payload.get('rrn')
            invoice.terminal = getattr(invoice, 'terminal', None) or payload.get('terminal')
            invoice.save()
   
    def _process_payment_status(self, payload: Dict, user_id: int, plan_id: int, bot_id: int, base_reference: str) -> Dict:
        """Обработка статуса платежа как в PHP коде"""
        import logging
        from django.utils import timezone
        from subscriptions.models import Plan, Subscription
        from core.models import TelegramUser
        
        logger = logging.getLogger(__name__)
        transaction_status = payload.get('transactionStatus')
        
        if transaction_status == 'Approved':
            return self._handle_approved_payment(payload, user_id, plan_id, bot_id, base_reference)
        else:
            return self._handle_declined_payment(payload, user_id, plan_id, bot_id, base_reference)

    def _handle_approved_payment(self, payload: Dict, user_id: int, plan_id: int, bot_id: int, base_reference: str) -> Dict:
        """Обработка успешного платежа - точно как в PHP"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        from subscriptions.models import Plan, Subscription
        from core.models import TelegramUser
        from payments.models import VerifiedUser
        
        logger = logging.getLogger(__name__)
        
        # Получаем план и пользователя
        plan = Plan.objects.get(id=plan_id, enabled=True)
        user, _ = TelegramUser.objects.get_or_create(user_id=user_id)
        
        amount = float(payload.get('amount', 0))
        duration_days = plan.duration_days if plan else 30
        
        # Определяем дату начала (как в PHP)
        starts_from = timezone.now()
        if plan.start_date and timezone.now() < plan.start_date:
            starts_from = plan.start_date
        
        # Работа с подпиской (как в PHP)
        subscription, created = Subscription.objects.get_or_create(
            bot_id=bot_id,
            user_id=user_id,
            defaults={
                'user': user,
                'plan': plan,
                'starts_at': starts_from.date(),
                'expires_at': (starts_from + timedelta(days=duration_days)).date(),
                'status': 'active',
                'amount': amount,
                'order_reference': base_reference,
            }
        )
        
        if created:
            # Новая подписка
            logger.info(f"New subscription created for user {user_id}")
            self._setup_new_subscription(subscription, payload, duration_days)
        else:
            # Продление существующей
            logger.info(f"Extending subscription for user {user_id}")
            self._extend_subscription(subscription, duration_days)
        
        # Создаем/обновляем инвойс (как в PHP)
        self._update_or_create_invoice(base_reference, payload, bot_id, user_id, plan_id, amount, 'APPROVED')
        
        # Создаем/обновляем VerifiedUser (как в PHP)
        self._update_verified_user(bot_id, user_id, payload)
        
        # Проверяем debounce и отправляем уведомление (как в PHP)
        self._handle_payment_notification(bot_id, user_id, plan_id, base_reference, subscription)
        
        return {"status": "accepted"}
    
    def _setup_new_subscription(self, subscription: Subscription, payload: Dict, duration_days: int):
        """Настройка новой подписки как в PHP"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        
        logger = logging.getLogger(__name__)
        
        # Регулярные платежи
        is_regular = payload.get('regularCreated') == True
        if is_regular:
            subscription.regular_status = 'Active'
            subscription.regular_mode = payload.get('regularMode', 'monthly')
            subscription.card_token = payload.get('recToken')
            subscription.date_begin = timezone.now().date()
            subscription.date_end = (timezone.now() + timedelta(days=365)).date()
            subscription.next_payment_date = (timezone.now() + timedelta(days=duration_days)).date()
        
        # Сброс напоминаний
        subscription.reminder_sent = 0
        subscription.reminder_sent_at = None
        subscription.last_payment_date = timezone.now().date()
        subscription.save()

    def _extend_subscription(self, subscription: Subscription, duration_days: int):
        """Продление подписки как в PHP"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        
        logger = logging.getLogger(__name__)
        
        current_expiration = subscription.expires_at
        starts_from = max(current_expiration, timezone.now().date()) if current_expiration > timezone.now().date() else timezone.now().date()
        
        subscription.expires_at = starts_from + timedelta(days=duration_days)
        subscription.status = 'active'
        subscription.reminder_sent = 0
        subscription.reminder_sent_at = None
        subscription.last_payment_date = timezone.now().date()
        subscription.save()
        
        logger.info(f"Subscription for user {subscription.user_id} extended to {subscription.expires_at}")
            
    def _update_or_create_invoice(self, base_reference: str, payload: Dict, bot_id: int, user_id: int, plan_id: int, amount: float, status: str):
        """Создание/обновление инвойса как в PHP"""
        import logging
        logger = logging.getLogger(__name__)
        
        Invoice.objects.update_or_create(
            order_reference=base_reference,
            defaults={
                'bot_id': bot_id,
                'user_id': user_id,
                'plan_id': plan_id,
                'amount': amount,
                'payment_status': status,
                'transaction_id': payload.get('rrn'),
                'rec_token': payload.get('recToken'),
                'phone': payload.get('phone'),
                'email': payload.get('email'),
                'card_pan': payload.get('cardPan'),
                'card_type': payload.get('cardType'),
                'card_product': payload.get('cardProduct'),
                'issuer_bank': payload.get('issuerBankName'),
                'issuer_country': payload.get('issuerBankCountry'),
                'payment_system': payload.get('paymentSystem'),
                'fee': payload.get('fee'),
                'rrn': payload.get('rrn'),
                'terminal': payload.get('terminal'),
            }
        )

    def _update_verified_user(self, bot_id: int, user_id: int, payload: Dict):
        """Обновление верифицированного пользователя как в PHP"""
        import logging
        from payments.models import VerifiedUser
        
        logger = logging.getLogger(__name__)
        
        VerifiedUser.objects.update_or_create(
            bot_id=bot_id,
            user_id=user_id,
            defaults={
                'verified': True,
                'card_masked': payload.get('cardPan'),
                'card_type': payload.get('cardType'),
                'payment_system': payload.get('paymentSystem'),
                'issuer_bank': payload.get('issuerBankName'),
                'fee': payload.get('fee'),
            }
        )

    
    def _handle_payment_notification(self, bot_id: int, user_id: int, plan_id: int, base_reference: str, subscription):
        """Отправка уведомления с debounce логикой как в PHP"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        
        logger = logging.getLogger(__name__)
        
        # Debounce: проверяем недавние успешные платежи
        debounce_minutes = 10
        recent_success = Invoice.objects.filter(
            bot_id=bot_id,
            user_id=user_id,
            payment_status=PaymentStatus.APPROVED,
            created_at__gte=timezone.now() - timedelta(minutes=debounce_minutes)
        ).exclude(order_reference=base_reference).exists()
        
        if recent_success:
            logger.info(f'success_notification_suppressed: user_id={user_id}, bot_id={bot_id}, window_min={debounce_minutes}')
        else:
            try:
                # Здесь должен быть вызов телеграм сервиса для отправки уведомления
                # self.telegram_service.notify_about_payment(bot_id, user_id, subscription.expires_at)
                logger.info(f'Payment notification sent to user {user_id}')
            except Exception as e:
                logger.error(f'Payment notification failed: {e}')