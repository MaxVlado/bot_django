# ================================================================
# wayforpay/api.py
# ================================================================
import hashlib
import hmac
from typing import Dict, List, Tuple, Optional
from django.conf import settings


class WayForPayAPI:
    """API для работы с WayForPay"""

    KEYS_FOR_REQUEST_SIGNATURE = [
        "merchantAccount",
        "merchantDomainName",
        "orderReference",
        "orderDate",
        "amount",
        "currency",
        "productName",
        "productCount",
        "productPrice",
    ]

    KEYS_FOR_RESPONSE_SIGNATURE = [
        "merchantAccount",
        "orderReference",
        "amount",
        "currency",
        "authCode",
        "cardPan",
        "transactionStatus",
        "reasonCode",
    ]

    
    def __init__(self, bot_id: int = None):
        if bot_id:
            from payments.models import MerchantConfig
            try:
                config = MerchantConfig.objects.select_related('bot').get(bot__bot_id=bot_id)
                self.merchant_account = config.merchant_account
                self.secret_key = config.secret_key
                self.payment_url = config.pay_url
                self.api_url = config.api_url
                # Добавляем недостающие атрибуты
                self.domain_name = config.bot.domain_name or "dev.astrocryptovoyager.com"
                self.return_url = f"https://{self.domain_name}/api/payments/wayforpay/return/"
                self.service_url = f"https://{self.domain_name}/api/payments/wayforpay/webhook/"
            except MerchantConfig.DoesNotExist:
                raise ValueError(f"MerchantConfig not found for bot_id={bot_id}")
        else:
            # Fallback на Django settings
            from django.conf import settings
            self.merchant_account = settings.WAYFORPAY_MERCHANT_ACCOUNT
            self.secret_key = settings.WAYFORPAY_SECRET_KEY
            self.domain_name = settings.WAYFORPAY_DOMAIN_NAME
            self.return_url = settings.WAYFORPAY_RETURN_URL
            self.service_url = settings.WAYFORPAY_SERVICE_URL
            self.payment_url = getattr(settings, "WAYFORPAY_PAY_URL", "https://secure.wayforpay.com/pay")
            self.api_url = getattr(settings, "WAYFORPAY_API_URL", "https://api.wayforpay.com/api")

    @staticmethod
    def _join(parts: List[str]) -> str:
        return ";".join("" if p is None else str(p) for p in parts)

    def _hmac_md5(self, s: str) -> str:
        return hmac.new(self.secret_key.encode("utf-8"), s.encode("utf-8"), hashlib.md5).hexdigest()

    def get_signature(self, data: Dict, keys: List[str]) -> str:
        """Генерация подписи по списку ключей (массивы product* разворачиваются)."""
        buf: List[str] = []
        for k in keys:
            if k not in data:
                continue
            v = data[k]
            if isinstance(v, list):
                buf.extend([str(x) for x in v])
            else:
                buf.append(str(v))
        return self._hmac_md5(self._join(buf))

    def get_request_signature(self, payload: Dict) -> str:
        return self.get_signature(payload, self.KEYS_FOR_REQUEST_SIGNATURE)

    def get_response_signature(self, payload: Dict) -> str:
        return self.get_signature(payload, self.KEYS_FOR_RESPONSE_SIGNATURE)

    def validate_response_signature(self, payload: Dict) -> bool:
        """Сравниваем без учета регистра."""
        received = (payload.get("merchantSignature") or "").lower()
        expected = self.get_response_signature(payload).lower()
        return received == expected

    def get_ack_signature(self, order_reference: str, status: str, t: int) -> str:
        return self._hmac_md5(self._join([order_reference, status, t]))

    def parse_order_reference(self, order_reference: str) -> Tuple[int, int, int, int]:
        """
        Поддержка обоих форматов:
        - WFP-<bot>-<user>-<plan>-<ts>
        - <bot>_<user>_<plan>_<ts>
        """
        s = order_reference
        if s.startswith("WFP-"):
            s = s[4:]
            parts = s.split("-")
        else:
            parts = s.split("_")
        if len(parts) < 4:
            raise ValueError(f"Invalid order_reference: {order_reference}")
        return int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])

    def generate_payment_form_data(self, invoice_data: Dict) -> Dict:
        """Генерация данных для формы/редиректа на страницу оплаты."""
        import time

        form_data = {
            "merchantAccount": self.merchant_account,
            "merchantAuthType": "SimpleSignature",
            "merchantDomainName": self.domain_name,
            "merchantTransactionSecureType": "AUTO",
            "orderReference": invoice_data["orderReference"],
            "orderDate": int(time.time()),
            "amount": int(invoice_data["amount"]),
            "currency": invoice_data["currency"],
            "returnUrl": self.return_url,
            "serviceUrl": self.service_url,
            "productName": invoice_data.get("productName", []),
            "productCount": invoice_data.get("productCount", []),
            'productPrice': [int(p) for p in invoice_data.get('productPrice', [])],
        }

        client = invoice_data.get("clientData") or {}
        form_data.update(client)

        form_data["merchantSignature"] = self.get_request_signature(form_data)
        return form_data
