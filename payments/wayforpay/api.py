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

    
    def __init__(self, merchant_config=None):
        if merchant_config:
            # Используем настройки конкретного бота из БД
            self.merchant_account = merchant_config.merchant_account
            self.secret_key = merchant_config.secret_key
            self.payment_url = merchant_config.pay_url
            self.api_url = merchant_config.api_url
            # domain_name, return_url, service_url берем из общих настроек
            self.domain_name = settings.WAYFORPAY_DOMAIN_NAME
            self.return_url = settings.WAYFORPAY_RETURN_URL
            self.service_url = settings.WAYFORPAY_SERVICE_URL
        else:
            # Fallback на общие настройки (для обратной совместимости)
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
        import logging
        logger = logging.getLogger(__name__)

        buf: List[str] = []
        for k in keys:
            if k not in data:
                continue
            v = data[k]

            if k in ["productName", "productCount", "productPrice"] and isinstance(v, list):
                buf.append(str(v[0]) if v else "")  # ИЗМЕНЕНО
            elif isinstance(v, list):
                buf.extend([str(x) for x in v])
            else:
                buf.append(str(v))

            # ДОБАВИТЬ ЛОГИРОВАНИЕ:
        sign_string = self._join(buf)

        logger.info(f"Signature keys used: {keys}")
        logger.info(f"Buffer values: {buf}")
        logger.info(f"FINAL signature string: '{sign_string}'")
        
        signature = self._hmac_md5(sign_string)
        logger.info(f"HMAC-MD5 result: {signature}")
        
        return signature
    
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

    
    def parse_order_reference(self, order_reference: str) -> Tuple[int, int, int]:
        """
        Парсинг orderReference формата: ORDER_1758606042kjI_407673079_2
        
        Также поддерживает рекуррентный формат с суффиксом:
        ORDER_1758606042kjI_407673079_2_WFPREG-1
        
        Возвращает: (user_id, plan_id, timestamp)
        
        Примечание: bot_id извлекается из Plan, не из orderReference
        """
        import re
        import logging
        logger = logging.getLogger(__name__)
        
        # Очистка: убираем точку с запятой и пробелы
        ref = order_reference.strip().rstrip(';')
        
        logger.info(f"Parsing orderReference: {ref}")
        
        # ⭐ НОВОЕ: Обрезаем суффикс _WFPREG-* для рекуррентных платежей
        if '_WFPREG-' in ref or '_WFPREG' in ref:
            # Находим базовый reference без суффикса
            base_ref = ref.split('_WFPREG')[0]
            logger.info(f"Detected recurring payment, using base reference: {base_ref}")
            ref = base_ref
        
        # Проверяем префикс ORDER_
        if not ref.startswith("ORDER_"):
            raise ValueError(f"Invalid orderReference format (must start with ORDER_): {order_reference}")
        
        # Убираем префикс ORDER_
        ref_without_prefix = ref[6:]  # "1758606042kjI_407673079_2"
        
        # Разделяем по подчёркиванию
        parts = ref_without_prefix.split('_')
        
        # Ожидаем 3 части: [timestamp+random, user_id, plan_id]
        if len(parts) != 3:
            raise ValueError(f"Invalid orderReference format (expected 3 parts): {order_reference}")
        
        try:
            # parts[0] = "1758606042kjI" - timestamp + 3 случайных символа
            # parts[1] = "407673079" - user_id
            # parts[2] = "2" - plan_id
            
            user_id = int(parts[1])
            plan_id = int(parts[2])
            
            # Извлекаем timestamp из первой части (берём только цифры в начале)
            timestamp_match = re.match(r'^(\d+)', parts[0])
            if not timestamp_match:
                raise ValueError(f"Cannot extract timestamp from: {parts[0]}")
            
            timestamp = int(timestamp_match.group(1))
            
            logger.info(f"✅ Parsed: user_id={user_id}, plan_id={plan_id}, timestamp={timestamp}")
            
            return user_id, plan_id, timestamp
            
        except (ValueError, IndexError) as e:
            raise ValueError(f"Cannot parse orderReference {order_reference}: {e}")
    
    def generate_payment_form_data(self, invoice_data: Dict) -> Dict:
        """Генерация данных для формы/редиректа на страницу оплаты."""
        import time
        import logging
        logger = logging.getLogger(__name__)

        form_data = {
            "transactionType": "CREATE_INVOICE",  # ДОБАВИТЬ
            "apiVersion": 1,  # ДОБАВИТЬ
            "merchantAccount": self.merchant_account,
            "merchantAuthType": "SimpleSignature",
            "merchantDomainName": self.domain_name,
            "merchantTransactionSecureType": "AUTO",
            "orderReference": invoice_data["orderReference"],
            "orderDate": int(time.time()),
            "amount": int(float(invoice_data["amount"])),  # Убрать .0
            'productPrice': [int(float(p)) for p in invoice_data.get('productPrice', [])],  # Убрать .0
            "currency": invoice_data["currency"],
            "returnUrl": self.return_url,
            "serviceUrl": self.service_url,
            "productName": invoice_data.get("productName", []),
            "productCount": invoice_data.get("productCount", []),
            "language": "UA"
        }

        client = invoice_data.get("clientData") or {}
        form_data.update(client)

        # ДОБАВИТЬ ЛОГИРОВАНИЕ:
        logger.info(f"Signature data before signing: {form_data}")
        logger.info(f"Domain name used: {self.domain_name}")
        logger.info(f"Secret key used: {self.secret_key[:10]}...")

        form_data["merchantSignature"] = self.get_request_signature(form_data)

        # ЛОГИРОВАНИЕ ПОСЛЕ:
        logger.info(f"Generated signature: {form_data['merchantSignature']}")
    
        return form_data
