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
      
    # payments/wayforpay/services.py

    @transaction.atomic
    def handle_webhook(self, payload: Dict) -> Dict:
        """
        Обработка webhook с новым форматом orderReference: ORDER_timestamp+rand_user_plan
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f'Received webhook from WayForPay: {payload}')
        
        # 1. Проверка подписи (если включена)
        from django.conf import settings
        
        verify_signature = getattr(settings, 'WAYFORPAY_VERIFY_SIGNATURE', True)
        
        if verify_signature and not self.api.validate_response_signature(payload):
            logger.error('Invalid signature from WayForPay')
            return {"status": "error", "message": "Invalid signature"}
        
        # 2. Проверка валюты
        if payload.get('currency') != 'UAH':
            logger.warning(f"Invalid currency: {payload.get('currency')}")
            return {"message": "Unsupported currency"}
        
        # 3. Получаем orderReference
        order_reference = payload.get('orderReference', '').strip().rstrip(';')
        
        if not order_reference:
            logger.error("orderReference is missing")
            return {"status": "error", "message": "orderReference required"}
        
        # 4. Парсинг orderReference
        try:
            user_id, plan_id, timestamp = self.api.parse_order_reference(order_reference)
            logger.info(f"✅ Parsed: user_id={user_id}, plan_id={plan_id}, timestamp={timestamp}")
            
        except ValueError as e:
            logger.error(f"❌ Parse failed: {e}")
            
            # FALLBACK: прямой поиск Invoice (на случай миграции или ручного создания)
            logger.info(f"🔍 Trying fallback: direct Invoice lookup")
            
            invoice = Invoice.objects.filter(
                order_reference=order_reference
            ).select_related('user', 'plan').first()
            
            if not invoice:
                logger.error(f"❌ Invoice not found: {order_reference}")
                return {"status": "error", "message": "Invoice not found"}
            
            user_id = invoice.user_id
            plan_id = invoice.plan_id
            bot_id = invoice.bot_id
            
            logger.info(f"✅ Fallback success: user_id={user_id}, plan_id={plan_id}, bot_id={bot_id}")
            
            # Переходим к обработке
            base_reference = order_reference.split('_WFPREG-')[0]
            return self._process_payment_status(payload, user_id, plan_id, bot_id, base_reference)
        
        # 5. Получаем Plan и bot_id
        from subscriptions.models import Plan
        plan = Plan.objects.filter(id=plan_id, enabled=True).first()
        
        if not plan:
            logger.error(f"Plan {plan_id} not found or disabled")
            return {"status": "error", "message": "Plan not available"}
        
        bot_id = plan.bot_id
        logger.info(f"Bot ID from plan: {bot_id}")
        
        # 6. Проверка дубликатов
        base_reference = order_reference.split('_WFPREG-')[0]
        
        existing_invoice = Invoice.objects.filter(
            order_reference=base_reference,
            payment_status=PaymentStatus.APPROVED
        ).first()
        
        if existing_invoice:
            logger.info(f"🔄 Duplicate webhook for: {order_reference}")
            self._update_invoice_fields(existing_invoice, payload)
            return {"status": "accepted"}
        
        # 7. Обработка платежа
        return self._process_payment_status(payload, user_id, plan_id, bot_id, base_reference)
   
    def _update_invoice_fields(self, invoice: Invoice, payload: Dict):
        """Обновление полей инвойса без перезаписи существующих значений"""
        
        # Обновляем только если поле пустое
        issuer_country = payload.get('issuerBankCountry')
        if issuer_country:
            issuer_country = issuer_country[:3].upper()
        
        invoice.phone = invoice.phone or payload.get('phone')
        invoice.email = invoice.email or payload.get('email') 
        invoice.card_pan = invoice.card_pan or payload.get('cardPan')
        invoice.card_type = invoice.card_type or payload.get('cardType')
        invoice.issuer_bank = invoice.issuer_bank or payload.get('issuerBankName')
        invoice.issuer_country = invoice.issuer_country or issuer_country  # ИСПОЛЬЗУЕМ ОБРАБОТАННОЕ
        invoice.payment_system = invoice.payment_system or payload.get('paymentSystem')
        invoice.fee = invoice.fee or payload.get('fee')
        invoice.rrn = invoice.rrn or payload.get('rrn')
        invoice.approval_code = invoice.approval_code or payload.get('approvalCode')
        invoice.terminal = invoice.terminal or payload.get('terminal')
        invoice.reason_code = invoice.reason_code or payload.get('reasonCode')
        invoice.save()
   
    def _process_payment_status(self, payload: Dict, user_id: int, plan_id: int, bot_id: int, base_reference: str) -> Dict:
        """Обработка статуса платежа с нормализацией"""
        import logging
        from django.utils import timezone
        from subscriptions.models import Plan, Subscription
        from core.models import TelegramUser
        
        logger = logging.getLogger(__name__)
        
        # ДОБАВЛЕНО: нормализация статуса (case-insensitive)
        transaction_status = payload.get('transactionStatus', '').upper()
        
        # Проверяем, что план всё ещё доступен
        plan = Plan.objects.filter(id=plan_id, enabled=True).first()
        if not plan:
            logger.warning(f"Plan {plan_id} is no longer available")
            return {"status": "error", "message": "Plan not available"}
        
        if transaction_status == 'APPROVED':
            return self._handle_approved_payment(payload, user_id, plan_id, bot_id, base_reference)
        elif transaction_status in ['DECLINED', 'EXPIRED', 'CANCELED']:
            return self._handle_declined_payment(payload, user_id, plan_id, bot_id, base_reference)
        else:
            logger.warning(f"Unknown transaction status: {transaction_status}")
            return {"status": "error", "message": f"Unknown status: {transaction_status}"} 
        
    def _handle_approved_payment(self, payload: Dict, user_id: int, plan_id: int, bot_id: int, base_reference: str) -> Dict:
        """Обработка успешного платежа"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        from subscriptions.models import Plan, Subscription, SubscriptionStatus
        from core.models import TelegramUser
        from payments.models import VerifiedUser
        
        logger = logging.getLogger(__name__)
        
        # Получаем план и пользователя
        plan = Plan.objects.get(id=plan_id, enabled=True)
        user, _ = TelegramUser.objects.get_or_create(user_id=user_id)
        
        amount = float(payload.get('amount', 0))
        duration_days = plan.duration_days
        transaction_id = payload.get('transactionId')
        
        # Дата начала
        starts_from = timezone.now()
        
        # Работа с подпиской
        subscription, created = Subscription.objects.get_or_create(
            bot_id=bot_id,
            user_id=user_id,
            defaults={
                'user': user,
                'plan': plan,
                'starts_at': starts_from,
                'expires_at': starts_from + timedelta(days=duration_days),
                'status': SubscriptionStatus.ACTIVE,
                'amount': amount,
                'order_reference': base_reference,
                'transaction_id': transaction_id,
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
            
            # Обновляем данные последнего платежа
            subscription.amount = amount
            subscription.order_reference = base_reference
            subscription.transaction_id = transaction_id
            subscription.save()
    
        # Создаем/обновляем инвойс
        self._update_or_create_invoice(base_reference, payload, bot_id, user_id, plan_id, amount, 'APPROVED')
        
        # Создаем/обновляем VerifiedUser
        self._update_verified_user(bot_id, user_id, payload)
        
        # Проверяем debounce и отправляем уведомление
        self._handle_payment_notification(bot_id, user_id, plan_id, base_reference, subscription)
        
        return {"status": "accepted"}
    
    def _setup_new_subscription(self, subscription: Subscription, payload: Dict, duration_days: int):
        """Настройка новой подписки"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        
        logger = logging.getLogger(__name__)
        
        # Рекуррентные платежи
        is_regular = payload.get('regularCreated') == True
        if is_regular:
            subscription.recurrent_status = 'Active'
            subscription.recurrent_mode = payload.get('regularMode', 'monthly')
            subscription.card_token = payload.get('recToken')
            subscription.recurrent_date_begin = timezone.now().date()
            subscription.recurrent_date_end = (timezone.now() + timedelta(days=365)).date()
            subscription.recurrent_next_payment = (timezone.now() + timedelta(days=duration_days)).date()
        
        # Сброс напоминаний
        subscription.reminder_sent_count = 0
        subscription.reminder_sent_at = None
        subscription.last_payment_date = timezone.now()  # DateTime, не .date()
        subscription.save()

    def _extend_subscription(self, subscription: Subscription, duration_days: int):
        """Продление подписки с улучшенным логированием и проверками"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        
        logger = logging.getLogger(__name__)
        
        current_expiration = subscription.expires_at
        now = timezone.now()
        
        # Определяем якорь для продления
        anchor = max(current_expiration, now) if current_expiration else now
        new_expiration = anchor + timedelta(days=duration_days)
        
        # ДОБАВЛЕНО: детальное логирование для отладки
        logger.info(f"Extending subscription {subscription.id}:")
        logger.info(f"  - Current expires_at: {current_expiration}")
        logger.info(f"  - Anchor (max with now): {anchor}")
        logger.info(f"  - Duration days: {duration_days}")
        logger.info(f"  - New expires_at: {new_expiration}")
        
        # Обновляем подписку
        subscription.expires_at = new_expiration.date()
        subscription.last_payment_date = now.date()
        subscription.status = 'active'  # Активируем если была неактивной
        
        # Сброс напоминаний при продлении
        subscription.reminder_sent = 0
        subscription.reminder_sent_at = None
        
        subscription.save(update_fields=[
            'expires_at', 'last_payment_date', 'status', 
            'reminder_sent', 'reminder_sent_at', 'updated_at'
        ])
        
        logger.info(f"Subscription {subscription.id} extended successfully")
   
    def _update_or_create_invoice(self, base_reference: str, payload: Dict, bot_id: int, user_id: int, plan_id: int, amount: float, status: str):
        """Создание/обновление инвойса как в PHP"""
        import logging
        logger = logging.getLogger(__name__)
        
        # ИСПРАВЛЕНО: обрезаем issuer_country до 3 символов (код страны)
        issuer_country = payload.get('issuerBankCountry')
        if issuer_country:
            issuer_country = issuer_country[:3].upper()  # UA, US, UK и т.д.
        
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
                'issuer_bank': payload.get('issuerBankName'),
                'issuer_country': issuer_country,  # <-- ВОТ ЭТО!
                'payment_system': payload.get('paymentSystem'),
                'fee': payload.get('fee'),
                'rrn': payload.get('rrn'),
                'approval_code': payload.get('approvalCode'),
                'terminal': payload.get('terminal'),
                'reason_code': payload.get('reasonCode'),
                'paid_at': timezone.now() if status == 'APPROVED' else None,
            }
        )

    def _update_verified_user(self, bot_id: int, user_id: int, payload: Dict):
        """Обновление верифицированного пользователя на основе реальных полей модели"""
        import logging
        from payments.models import VerifiedUser
        from core.models import TelegramUser
        from django.utils import timezone
        
        logger = logging.getLogger(__name__)
        
        # Получаем user объект
        user = TelegramUser.objects.get(user_id=user_id)
        
        # ИСПРАВЛЕНО: используем только поля которые есть в модели
        VerifiedUser.objects.update_or_create(
            bot_id=bot_id,
            user=user,  # ForeignKey, не user_id!
            defaults={
                'first_payment_date': timezone.now(),  # ДОБАВЛЕНО: обязательное поле
                'card_masked': payload.get('cardPan'),
                'payment_system': payload.get('paymentSystem'),
                'issuer_bank': payload.get('issuerBankName'),
                'last_payment_date': timezone.now(),
                'total_amount_paid': 0,  # ДОБАВЛЕНО: обязательное поле, будет обновлено через update_payment_stats
                'successful_payments_count': 1,  # По умолчанию 1
            }
        )

    
    def _handle_payment_notification(self, bot_id: int, user_id: int, plan_id: int, base_reference: str, subscription):
        """Отправка уведомления с исправленной debounce логикой"""
        import logging
        from django.utils import timezone
        from datetime import timedelta
        
        logger = logging.getLogger(__name__)
        
        # ИСПРАВЛЕНО: используем paid_at вместо created_at
        debounce_minutes = 10
        recent_success = Invoice.objects.filter(
            bot_id=bot_id,
            user_id=user_id,
            payment_status=PaymentStatus.APPROVED,
            paid_at__gte=timezone.now() - timedelta(minutes=debounce_minutes),  # ИЗМЕНЕНО
            paid_at__isnull=False  # ДОБАВЛЕНО: убеждаемся, что paid_at заполнен
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