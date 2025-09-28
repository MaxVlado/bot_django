# ================================================================
# wayforpay/views.py
# ================================================================
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from payments.models import Invoice, PaymentStatus
from .services import WayForPayService


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
    """API: обработка вебхука WayForPay."""

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            data = json.loads(request.body.decode("utf-8"))
            logger.info(f"Invoice create request: {data}")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("invalid json")

        bot_id = int(data.get("bot_id", 0))
        user_id = int(data.get("user_id", 0))
        plan_id = int(data.get("plan_id", 0))
        
        logger.info(f"Creating invoice for bot_id={bot_id}, user_id={user_id}, plan_id={plan_id}")
        
        if not bot_id or not user_id or not plan_id:
            return HttpResponseBadRequest("bot_id, user_id, plan_id are required")

        svc = WayForPayService()
        logger.info(f"WayForPayService created, API merchant_account: {svc.api.merchant_account}")
        
        try:
            url = svc.create_invoice(bot_id=bot_id, user_id=user_id, plan_id=plan_id)
            logger.info(f"Invoice URL created: {url}")
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            return JsonResponse({"ok": False, "error": str(e)}, status=422)

        return JsonResponse({"ok": True, "invoiceUrl": url})

@method_decorator(csrf_exempt, name="dispatch")


class ReturnView(View):
    """Обработка возврата пользователя с платёжной страницы (без гарантий вебхука)."""

    def get(self, request):
        order_reference = request.GET.get("orderReference")
        if not order_reference:
            # тест ждёт status='error' и сообщение с 'orderReference'
            return JsonResponse({"status": "error", "message": "Missing orderReference"})

        try:
            inv = Invoice.objects.get(order_reference=order_reference)
        except Invoice.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Invoice not found"})

        if inv.payment_status == PaymentStatus.APPROVED:
            return JsonResponse({
                "status": "success",
                "invoice_id": inv.id,
                "amount": int(inv.amount),
                "currency": inv.currency,
                "payment_status": inv.payment_status,
                "subscription_id": inv.subscription_id,
            })

        # вебхук ещё не пришёл / платёж не подтверждён
        return JsonResponse({
            "status": "pending",
            "invoice_id": inv.id,
            "amount": int(inv.amount),
            "currency": inv.currency,
            "payment_status": inv.payment_status,
        })