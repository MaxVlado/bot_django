# wayforpay/middleware.py
from time import time
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

class WebhookRateLimitMiddleware(MiddlewareMixin):
    """
    Простейший rate limit по IP для пути /api/payments/wayforpay/webhook/
    Включается только если WAYFORPAY_RATELIMIT_ENABLED=True.
    """
    def process_request(self, request):
        if not getattr(settings, "WAYFORPAY_RATELIMIT_ENABLED", False):
            return None
        if request.path != "/api/payments/wayforpay/webhook/":
            return None

        # IP из X-Forwarded-For или REMOTE_ADDR
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
              or request.META.get("REMOTE_ADDR", ""))
        if not ip:
            ip = "unknown"

        window = int(getattr(settings, "WAYFORPAY_RATELIMIT_WINDOW", 10))   # сек
        limit  = int(getattr(settings, "WAYFORPAY_RATELIMIT_COUNT", 5))     # запросов/окно
        key = f"wfp:rl:{ip}"
        now = int(time())

        data = cache.get(key)
        if not data:
            cache.set(key, {"count": 1, "start": now}, timeout=window)
            return None

        count = int(data.get("count", 0))
        start = int(data.get("start", now))

        # новое окно
        if now - start >= window:
            cache.set(key, {"count": 1, "start": now}, timeout=window)
            return None

        # превышение лимита
        if count + 1 > limit:
            return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)

        # инкремент в том же окне
        data["count"] = count + 1
        cache.set(key, data, timeout=max(1, window - (now - start)))
        return None
