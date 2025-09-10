# ================================================================
# wayforpay/urls.py
# ================================================================
from django.urls import path
from .views import InvoiceCreateView, WebhookView, ReturnView

app_name = 'wayforpay'

urlpatterns = [
    path('create-invoice/', InvoiceCreateView.as_view(), name='create_invoice'),
    path('webhook/', WebhookView.as_view(), name='webhook'),
    path('return/', ReturnView.as_view(), name='return'),
]