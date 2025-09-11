

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health_view(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_view), 
    # WayForPay endpoints (из payments/wayforpay/urls.py)
    path(
        "api/payments/wayforpay/",
        include(("payments.wayforpay.urls", "wayforpay"), namespace="wayforpay"),
    ),
]
