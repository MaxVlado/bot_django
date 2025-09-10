from django.db import models


class PaymentNotification(models.Model):
    """
    Идемпотентность уведомлений об успешной оплате.
    Ключ — order_reference (одна запись = одно «успешное» уведомление по этому референсу).
    """
    order_reference = models.CharField(max_length=255, primary_key=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bot_payment_notifications"
        verbose_name = "Уведомление об успехе оплаты"
        verbose_name_plural = "Уведомления об успехе оплаты"

    def __str__(self) -> str:
        return f"{self.order_reference} @ {self.sent_at:%Y-%m-%d %H:%M:%S}"


class ExpiryNotification(models.Model):
    """
    Идемпотентность напоминаний об окончании подписки.
    Ключ — (bot_id, tg_user_id, expires_on): одно напоминание за день.
    """
    bot_id = models.IntegerField()
    tg_user_id = models.BigIntegerField()
    expires_on = models.DateField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bot_expiry_notifications"
        unique_together = (("bot_id", "tg_user_id", "expires_on"),)
        indexes = [
            models.Index(fields=["bot_id", "expires_on"]),
            models.Index(fields=["tg_user_id"]),
        ]
        verbose_name = "Напоминание об окончании подписки"
        verbose_name_plural = "Напоминания об окончании подписки"

    def __str__(self) -> str:
        return f"bot={self.bot_id} user={self.tg_user_id} on={self.expires_on}"
