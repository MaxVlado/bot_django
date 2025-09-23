import pytest
from core.models import Bot
from payments.models import MerchantConfig
import bot_runner
from fastapi.testclient import TestClient
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.covers("A6.1")
def test_e2e_create_bot_and_webhook(tmp_path):
    """A6.1: Создание Bot + MerchantConfig → запуск процесса → Telegram webhook принят"""
    log_file = tmp_path / "e2e_bot.log"
    bot = Bot.objects.create(bot_id=800, title="E2E Bot", username="e2e_bot", token="XYZ", port=8123, log_path=str(log_file))
    MerchantConfig.objects.create(bot=bot, merchant_account="acc", secret_key="key")

    # имитация запуска webhook
    bot_runner.BOT = bot
    client = TestClient(bot_runner.app)

    response = client.post("/webhook")
    assert response.status_code == 200
    assert response.json()["ok"] is True

# @pytest.mark.django_db
# @pytest.mark.covers("A6.2")
# def test_e2e_logs_written_and_viewable(tmp_path, admin_client):
#     """A6.2: Bot пишет логи в log_path, View Logs показывает последние записи"""
#     log_base = tmp_path / "e2e_bot"
#     log_out = log_base.with_suffix(".out.log")
#     log_out.write_text("line1\nline2\nline3\n")
#
#     bot = Bot.objects.create(
#         bot_id=801,
#         title="LogE2E",
#         username="log_e2e",
#         token="XYZ",
#         log_path=str(log_base)   # сохраняем базу, без .out.log
#     )
#
#     url = reverse("admin:core_bot_logs_out", args=[bot.id])
#     response = admin_client.get(url)
#
#     assert response.status_code == 200
#     html = response.content.decode()
#     assert "line2" in html
#     assert "line3" in html
#
# @pytest.mark.django_db
# @pytest.mark.covers("A6.3")
# def test_e2e_err_logs_written_and_viewable(tmp_path, admin_client):
#     """A6.3: Bot пишет ошибки в log_path, View Err Logs показывает последние записи"""
#     log_base = tmp_path / "e2e_bot"
#     log_err = log_base.with_suffix(".err.log")
#     log_err.write_text("err1\nerr2\nerr3\n")
#
#     bot = Bot.objects.create(
#         bot_id=802,
#         title="LogE2E_Err",
#         username="log_e2e_err",
#         token="XYZ",
#         log_path=str(log_base),
#     )
#
#     url = reverse("admin:core_bot_logs_err", args=[bot.id])
#     response = admin_client.get(url)
#
#     assert response.status_code == 200
#     html = response.content.decode()
#     assert "err2" in html
#     assert "err3" in html
