# payments/wayforpay/views.py

import json
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from payments.models import Invoice, PaymentStatus
from .services import WayForPayService
from core.models import Bot



@method_decorator(csrf_exempt, name="dispatch")
class InvoiceCreateView(View):
    """API: создание инвойса (бот дергает этот endpoint)."""

    def post(self, request):
        try:
            data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("invalid json")

        bot_id = int(data.get("bot_id", 0))
        user_id = int(data.get("user_id", 0))
        plan_id = int(data.get("plan_id", 0))
        
        if not bot_id or not user_id or not plan_id:
            return HttpResponseBadRequest("bot_id, user_id, plan_id are required")

        svc = WayForPayService()
        try:
            url = svc.create_invoice(bot_id=bot_id, user_id=user_id, plan_id=plan_id)
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=422)

        return JsonResponse({"ok": True, "invoiceUrl": url})


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    """API: обработка вебхука от WayForPay."""

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            payload = json.loads(request.body.decode("utf-8"))
            logger.info(f"Webhook received from WayForPay: {payload}")
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook")
            return HttpResponseBadRequest("invalid json")

        # Обрабатываем webhook через сервис
        svc = WayForPayService()
        
        try:
            result = svc.handle_webhook(payload)
            logger.info(f"Webhook processed: {result}")
            
            # Возвращаем ответ для WayForPay
            return JsonResponse(result, status=200)
            
        except Exception as e:
            # Критические DB ошибки пробрасываем - нужен 5xx для ретрая WFP
            from django.db import utils as db_utils
            if isinstance(e, (db_utils.OperationalError, db_utils.IntegrityError)):
                logger.error(f"Critical DB error in webhook: {e}", exc_info=True)
                raise  # Пробрасываем для 5xx
            
            # Остальные ошибки логируем и возвращаем accept
            logger.error(f"Webhook processing error: {e}", exc_info=True)
            return JsonResponse({"status": "accept", "message": str(e)}, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class ReturnView(View):
    """Обработка возврата пользователя с платёжной страницы."""
    
    def get(self, request):
        order_reference = request.GET.get('orderReference')
        
        # Если нет orderReference - редирект на бота
        if not order_reference:
            try:
                bot = Bot.objects.filter(is_enabled=True).first()
                if bot:
                    bot_username = bot.username
                    return HttpResponse(f"""
                        <html>
                        <head>
                            <title>Оплата завершена</title>
                            <meta http-equiv="refresh" content="3;url=https://t.me/{bot_username}">
                        </head>
                        <body style="font-family: Arial; text-align: center; padding: 50px;">
                            <h1>✅ Оплата обработана!</h1>
                            <p>Возвращаем вас в Telegram бот...</p>
                            <p><a href="https://t.me/{bot_username}" style="font-size: 20px;">Открыть бот @{bot_username}</a></p>
                        </body>
                        </html>
                    """)
            except:
                pass
            
            # Если бот не найден - общая страница без редиректа
            return HttpResponse("""
                <html>
                <head><title>Оплата завершена</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>✅ Оплата обработана!</h1>
                    <p>Вернитесь в Telegram бот для проверки статуса.</p>
                </body>
                </html>
            """)
        
        # Ищем Invoice
        try:
            invoice = Invoice.objects.get(order_reference=order_reference)
        except Invoice.DoesNotExist:
            return JsonResponse({
                "status": "error", 
                "error": "Invoice not found"
            })
        
        # Определяем статус для пользователя
        if invoice.payment_status == PaymentStatus.APPROVED:
            status = "approved"
        elif invoice.payment_status == PaymentStatus.DECLINED:
            status = "declined"
        else:  # PENDING и все остальные
            status = "pending"
        
        return JsonResponse({
            "status": status,
            "payment_status": invoice.payment_status.value if hasattr(invoice.payment_status, 'value') else str(invoice.payment_status),
            "orderReference": order_reference
        })

    def post(self, request):
        return self.get(request)