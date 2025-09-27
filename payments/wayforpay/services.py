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
        self.bot_id = bot_id
        self.api = WayForPayAPI(bot_id=bot_id)

    @transaction.atomic
    def create_invoice(self, bot_id: int, user_id: int, plan_id: int, amount: Optional[Decimal] = None) -> str:
        # Создай сервис с конкретным bot_id
        service = WayForPayService(bot_id=bot_id)
        
        # Остальная логика остается той же...
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

        import urllib.parse
        params = urllib.parse.urlencode(form_data, doseq=True)
        return f"{self.api.payment_url}?{params}"

    @transaction.atomic
    def handle_webhook(self, payload: Dict) -> Dict:
        """
               Обработка webhook от WayForPay.
               Всегда отвечаем 'accept', чтобы WFP не ретраил.
               При верификации подписи/мерчанта — просто игнорируем неверные, не меняя состояние.
               """
        # 0) строгая проверка подписи/мерчанта (в проде)
        if getattr(settings, "WAYFORPAY_VERIFY_SIGNATURE", True):
            is_valid = self.api.validate_response_signature(payload)
            merch_ok = (payload.get("merchantAccount") == self.api.merchant_account)
            if not (is_valid and merch_ok):
                import time
                t = int(time.time())
                return {
                    "orderReference": payload.get("orderReference", ""),
                    "status": "accept",
                    "time": t,
                    "signature": self.api.get_ack_signature(payload.get("orderReference", ""), "accept", t),
                }

        # 0.5) защита от replay по TTL: слишком старые вебхуки игнорируем (но ACK отдаем)
        ttl_sec = int(getattr(settings, "WAYFORPAY_WEBHOOK_TTL_SECONDS", 0) or 0)
        if ttl_sec > 0:
            ts = payload.get("processingDate") or payload.get("orderDate") or payload.get("time")
            try:
                ts_int = int(ts) if ts is not None else None
            except (TypeError, ValueError):
                ts_int = None
            if ts_int:
                import time
                if int(time.time()) - ts_int > ttl_sec:
                    t = int(time.time())
                    return {
                        "orderReference": payload.get("orderReference", ""),
                        "status": "accept",
                        "time": t,
                        "signature": self.api.get_ack_signature(payload.get("orderReference", ""), "accept", t),
                    }

        order_reference = payload.get("orderReference")
        try:
            inv = Invoice.objects.select_for_update().get(order_reference=order_reference)
        except Invoice.DoesNotExist:
            import time
            t = int(time.time())
            return {
                "orderReference": order_reference or "",
                "status": "accept",
                "time": t,
                "signature": self.api.get_ack_signature(order_reference or "", "accept", t),
            }
        """
        Обработка webhook от WayForPay.
        Всегда отвечаем 'accept', чтобы WFP не ретраил.
        При верификации подписи/мерчанта — просто игнорируем неверные, не меняя состояние.
        """
        # 0) строгая проверка подписи/мерчанта (в проде)
        if getattr(settings, "WAYFORPAY_VERIFY_SIGNATURE", True):
            is_valid = self.api.validate_response_signature(payload)
            merch_ok = (payload.get("merchantAccount") == self.api.merchant_account)
            if not (is_valid and merch_ok):
                # принимаем, но ничего не делаем
                import time
                t = int(time.time())
                return {
                    "orderReference": payload.get("orderReference", ""),
                    "status": "accept",
                    "time": t,
                    "signature": self.api.get_ack_signature(payload.get("orderReference", ""), "accept", t),
                }

        order_reference = payload.get("orderReference")
        try:
            inv = Invoice.objects.select_for_update().get(order_reference=order_reference)
        except Invoice.DoesNotExist:
            import time
            t = int(time.time())
            return {
                "orderReference": order_reference or "",
                "status": "accept",
                "time": t,
                "signature": self.api.get_ack_signature(order_reference or "", "accept", t),
            }

        # 1) идемпотентность: если уже APPROVED и снова пришёл APPROVED — выходим
        tx_status = (payload.get("transactionStatus") or "").upper()

        if inv.payment_status == PaymentStatus.APPROVED and tx_status == "APPROVED":
            import time
            t = int(time.time())
            return {
                "orderReference": order_reference,
                "status": "accept",
                "time": t,
                "signature": self.api.get_ack_signature(order_reference, "accept", t),
            }

        # 2) защита от даунгрейда: не занижаем статус c APPROVED на DECLINED/REFUNDED/EXPIRED
        if inv.payment_status == PaymentStatus.APPROVED and tx_status in {"DECLINED", "REFUNDED", "EXPIRED"}:
            import time
            t = int(time.time())
            return {
                "orderReference": order_reference,
                "status": "accept",
                "time": t,
                "signature": self.api.get_ack_signature(order_reference, "accept", t),
            }

        # 3) обычная обработка
        self.process_payment_response(payload, inv)

        import time
        t = int(time.time())
        return {
            "orderReference": order_reference,
            "status": "accept",
            "time": t,
            "signature": self.api.get_ack_signature(order_reference, "accept", t),
        }

    @transaction.atomic
    def process_payment_response2(self, response_data: Dict, invoice: Optional[Invoice] = None) -> Invoice:
        """
        Обработка ответа о платеже:
        - Проверяем сумму/валюту перед APPROVED (иначе игнор)
        - Идемпотентность: повторный APPROVED по тому же orderReference не продлевает
        - Не даунгрейдим оплаченный инвойс (REFUNDED/… не понижают статус и не трогают подписку)
        """
        if invoice is None:
            # берём под блокировку для защиты от гонок
            invoice = Invoice.objects.select_for_update().get(order_reference=response_data["orderReference"])

        # сохранить вебхук целиком
        invoice.raw_response_payload = response_data

        status = (response_data.get("transactionStatus") or "").upper()

        # Маппинг полей WayForPay → Invoice (оставляем как было)
        invoice.transaction_id = response_data.get("transactionId") or response_data.get("transactionUniqueId")
        invoice.auth_code = response_data.get("authCode")
        invoice.card_pan = response_data.get("cardPan")
        invoice.card_type = response_data.get("cardType")
        invoice.issuer_bank = response_data.get("issuerBankName")
        invoice.issuer_country = response_data.get("issuerBankCountry")
        invoice.payment_system = response_data.get("paymentSystem") or response_data.get("cardProduct")
        invoice.reason_code = response_data.get("reasonCode")
        invoice.fee = response_data.get("fee")
        invoice.rrn = response_data.get("rrn")
        invoice.approval_code = response_data.get("approvalCode")
        invoice.terminal = response_data.get("terminal")
        invoice.rec_token = response_data.get("recToken")
        invoice.notified_at = timezone.now()

        # помощник для сравнения сумм (мы используем целые)
        def _to_int_or_none(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        payload_amount = _to_int_or_none(response_data.get("amount"))
        invoice_amount = _to_int_or_none(invoice.amount)
        payload_currency = (response_data.get("currency") or "").upper()
        invoice_currency = (invoice.currency or "").upper()

        # ---- логика статусов ----
        if status == "APPROVED":
            # сумма/валюта обязаны совпадать с инвойсом
            if payload_amount != invoice_amount or payload_currency != invoice_currency:
                # ничего не подтверждаем, просто фиксируем raw и техполя
                invoice.save(update_fields=[
                    "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                    "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                    "approval_code", "terminal", "rec_token", "notified_at", "updated_at",
                ])
                return invoice

            # идемпотентность: уже был APPROVED → не продлевать повторно
            if invoice.payment_status == PaymentStatus.APPROVED:
                invoice.save(update_fields=[
                    "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                    "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                    "approval_code", "terminal", "rec_token", "notified_at", "updated_at",
                ])
                return invoice

            # подтверждаем впервые
            invoice.payment_status = PaymentStatus.APPROVED
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=[
                "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                "approval_code", "terminal", "rec_token", "notified_at", "payment_status", "paid_at", "updated_at",
            ])
            self._process_successful_payment(invoice)

        elif status == "DECLINED":
            # не даунгрейдим оплаченный инвойс
            if invoice.payment_status != PaymentStatus.APPROVED:
                invoice.payment_status = PaymentStatus.DECLINED
            invoice.save(update_fields=[
                "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                "approval_code", "terminal", "rec_token", "notified_at", "payment_status", "updated_at",
            ])

        elif status in {"REFUNDED", "REVERSED", "CHARGEBACK"}:
            # политика: не трогаем статус и подписку, просто фиксируем payload
            invoice.save(update_fields=[
                "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                "approval_code", "terminal", "rec_token", "notified_at", "updated_at",
            ])

        elif status == "EXPIRED":
            # не даунгрейдим оплаченный инвойс
            if invoice.payment_status != PaymentStatus.APPROVED:
                invoice.payment_status = PaymentStatus.EXPIRED
            invoice.save(update_fields=[
                "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                "approval_code", "terminal", "rec_token", "notified_at", "payment_status", "updated_at",
            ])

        else:
            # промежуточные статусы: PENDING/IN_PROCESS/WAITING_AUTH_COMPLETE и т.п.
            # оставляем как есть (обычно PENDING/NEW)
            invoice.save(update_fields=[
                "raw_response_payload", "notified_at", "updated_at",
            ])

        return invoice



    @transaction.atomic
    def process_payment_response(self, response_data: dict, invoice: Invoice | None = None) -> Invoice:
        """
        Обработка ответа о платеже — идемпотентная и безопасная при гонках:
          - блокируем Invoice (select_for_update) для совместимости с Postgres
          - основная защита — CAS-апдейт: APPROVED ставится только если ещё не APPROVED
          - не даунгрейдим APPROVED на DECLINED/REFUNDED/EXPIRED
          - обновляем аудит-поля (raw_response_payload и пр.) во всех ветках
        """
        order_reference = response_data["orderReference"]

        # 1) Берём и БЛОКИРУЕМ инвойс (в т.ч. если передали объект — перечитаем с блокировкой)
        if invoice is None:
            invoice = (
                Invoice.objects
                .select_for_update()
                .get(order_reference=order_reference)
            )
        else:
            invoice = (
                Invoice.objects
                .select_for_update()
                .get(pk=invoice.pk)
            )

        # 2) Разбираем статус и заполняем аудит-поля (пока без сохранения)
        status = (response_data.get("transactionStatus") or "").upper()

        invoice.raw_response_payload = response_data
        invoice.transaction_id = response_data.get("transactionId") or response_data.get("transactionUniqueId")
        invoice.auth_code = response_data.get("authCode")
        invoice.card_pan = response_data.get("cardPan")
        invoice.card_type = response_data.get("cardType")
        invoice.issuer_bank = response_data.get("issuerBankName")
        invoice.issuer_country = response_data.get("issuerBankCountry")
        invoice.payment_system = response_data.get("paymentSystem") or response_data.get("cardProduct")
        invoice.reason_code = response_data.get("reasonCode")
        invoice.fee = response_data.get("fee")
        invoice.rrn = response_data.get("rrn")
        invoice.approval_code = response_data.get("approvalCode")
        invoice.terminal = response_data.get("terminal")
        invoice.rec_token = response_data.get("recToken")
        invoice.notified_at = timezone.now()

        # 3) Валидация суммы/валюты (терпим float/Decimal; валюта case-insensitive)
        payload_amount = response_data.get("amount")
        payload_currency = (response_data.get("currency") or "").upper()
        try:
            inv_amount = int(invoice.amount)
            pay_amount = int(float(payload_amount)) if payload_amount is not None else None
        except (TypeError, ValueError):
            pay_amount = None
        amount_ok = (pay_amount is not None and inv_amount == pay_amount)
        currency_ok = (payload_currency == (invoice.currency or "").upper())
        amounts_match = amount_ok and currency_ok

        # 4) Если уже APPROVED — просто фиксируем аудит и выходим (идемпотентность)
        if invoice.payment_status == PaymentStatus.APPROVED:
            invoice.save(update_fields=[
                "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                "approval_code", "terminal", "rec_token", "notified_at", "updated_at",
            ])
            return invoice

        # 5) APPROVED c совпадающими суммой/валютой — CAS-апдейт
        if status == "APPROVED" and amounts_match:
            now = timezone.now()

            # Пытаемся «выиграть гонку»: перевести в APPROVED только если ещё не APPROVED.
            updated = (
                Invoice.objects
                .filter(pk=invoice.pk)
                .exclude(payment_status=PaymentStatus.APPROVED)
                .update(payment_status=PaymentStatus.APPROVED, paid_at=now, notified_at=now, updated_at=now)
            )

            if updated == 0:
                # Проиграли гонку: другой поток уже одобрил. Обновим аудит и выйдем.
                invoice.refresh_from_db()
                invoice.raw_response_payload = response_data
                invoice.transaction_id = response_data.get("transactionId") or response_data.get("transactionUniqueId")
                invoice.auth_code = response_data.get("authCode")
                invoice.card_pan = response_data.get("cardPan")
                invoice.card_type = response_data.get("cardType")
                invoice.issuer_bank = response_data.get("issuerBankName")
                invoice.issuer_country = response_data.get("issuerBankCountry")
                invoice.payment_system = response_data.get("paymentSystem") or response_data.get("cardProduct")
                invoice.reason_code = response_data.get("reasonCode")
                invoice.fee = response_data.get("fee")
                invoice.rrn = response_data.get("rrn")
                invoice.approval_code = response_data.get("approvalCode")
                invoice.terminal = response_data.get("terminal")
                invoice.rec_token = response_data.get("recToken")
                invoice.save(update_fields=[
                    "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                    "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                    "approval_code", "terminal", "rec_token", "updated_at"
                ])
                return invoice

            # Мы победили: перечитаем, допишем аудит и обработаем подписку
            invoice.refresh_from_db()
            invoice.raw_response_payload = response_data
            invoice.transaction_id = response_data.get("transactionId") or response_data.get("transactionUniqueId")
            invoice.auth_code = response_data.get("authCode")
            invoice.card_pan = response_data.get("cardPan")
            invoice.card_type = response_data.get("cardType")
            invoice.issuer_bank = response_data.get("issuerBankName")
            invoice.issuer_country = response_data.get("issuerBankCountry")
            invoice.payment_system = response_data.get("paymentSystem") or response_data.get("cardProduct")
            invoice.reason_code = response_data.get("reasonCode")
            invoice.fee = response_data.get("fee")
            invoice.rrn = response_data.get("rrn")
            invoice.approval_code = response_data.get("approvalCode")
            invoice.terminal = response_data.get("terminal")
            invoice.rec_token = response_data.get("recToken")
            invoice.save(update_fields=[
                "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                "approval_code", "terminal", "rec_token", "updated_at"
            ])

            # Создание/продление подписки — ровно один раз (только победитель делает это)
            self._process_successful_payment(invoice)
            return invoice

        # 6) Отрицательные финальные статусы — фиксируем, но подписку не трогаем
        if status in {"DECLINED", "REFUNDED", "EXPIRED"}:
            invoice.payment_status = status
            invoice.save(update_fields=[
                "raw_response_payload", "transaction_id", "auth_code", "card_pan", "card_type",
                "issuer_bank", "issuer_country", "payment_system", "reason_code", "fee", "rrn",
                "approval_code", "terminal", "rec_token", "notified_at", "payment_status", "updated_at",
            ])
            return invoice

        # 7) Промежуточные/непонятные статусы — оставляем PENDING, но аудит фиксируем
        invoice.payment_status = PaymentStatus.PENDING
        invoice.save(update_fields=["raw_response_payload", "notified_at", "payment_status", "updated_at"])
        return invoice

    def _process_successful_payment(self, invoice: Invoice):
        from subscriptions.models import Subscription
        from subscriptions.services import SubscriptionService

        # снапшот длительности, если он был зафиксирован при создании инвойса
        snap_days = None
        if isinstance(getattr(invoice, "raw_request_payload", None), dict):
            val = invoice.raw_request_payload.get("planDurationDays")
            if val is not None:
                try:
                    snap_days = int(val)
                except (TypeError, ValueError):
                    snap_days = None

        # Ищем подписку по пользователю и боту (план не переключаем)
        existing = Subscription.objects.filter(user=invoice.user, bot_id=invoice.bot_id).first()

        if existing:
            SubscriptionService.extend_subscription(existing, paid_at=invoice.paid_at, invoice=invoice)
            subscription = existing
        else:
            # создаём с учётом снапшота (если он есть)
            subscription = SubscriptionService.create_subscription(invoice.user, invoice.plan, duration_days=snap_days)
            subscription.status = 'active'
            # важно: при первом успешном платеже сохраняем recToken/cardPan, если есть
            if invoice.rec_token:
                subscription.card_token = invoice.rec_token
                subscription.card_masked = invoice.card_pan
            subscription.save(update_fields=["status", "card_token", "card_masked", "updated_at"])

        # привязываем инвойс к подписке
        invoice.subscription = subscription
        invoice.save(update_fields=["subscription", "updated_at"])

        # верификация плательщика
        from payments.models import VerifiedUser
        VerifiedUser.verify_user_from_payment(invoice)

