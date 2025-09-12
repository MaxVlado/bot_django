import pytest
from django.urls import reverse
from core.models import Bot
from payments.models import MerchantConfig

@pytest.mark.django_db
@pytest.mark.covers("A1.1")
def test_admin_can_create_bot_with_inline_merchant_config(admin_client):
    """A1.1: Создание Bot в админке с inline MerchantConfig"""
    url = reverse("admin:core_bot_add")

    data = {
        "bot_id": 123,
        "title": "Test Bot",
        "username": "test_bot",
        "token": "12345:AAATESTTOKEN",
        "is_enabled": True,

        "merchant_config-0-merchant_account": "test_account",
        "merchant_config-0-secret_key": "test_secret",
        "merchant_config-0-pay_url": "https://secure.wayforpay.com/pay",
        "merchant_config-0-api_url": "https://api.wayforpay.com/api",
        "merchant_config-0-verify_signature": "on",
        "merchant_config-0-id": "",

        # management form
        "merchant_config-TOTAL_FORMS": "1",
        "merchant_config-INITIAL_FORMS": "0",
        "merchant_config-MIN_NUM_FORMS": "0",
        "merchant_config-MAX_NUM_FORMS": "1",

        # эмуляция нажатия кнопки Save
        "_save": "Save",
    }

    response = admin_client.post(url, data, follow=True)
    assert response.status_code == 200

    bot = Bot.objects.get(bot_id=123)
    mc = MerchantConfig.objects.get(bot=bot)

    assert mc.merchant_account == "test_account"
    assert mc.secret_key == "test_secret"
    assert mc.verify_signature is True


@pytest.mark.django_db
@pytest.mark.covers("A1.2")
def test_admin_can_edit_merchant_config(admin_client):
    """A1.2: Редактирование MerchantConfig сохраняется корректно"""
    # Создаём бота и конфиг напрямую
    bot = Bot.objects.create(bot_id=200, title="Edit Bot", username="edit_bot", token="XYZ")
    mc = MerchantConfig.objects.create(
        bot=bot,
        merchant_account="old_account",
        secret_key="old_secret",
    )

    url = reverse("admin:core_bot_change", args=[bot.id])

    data = {
        "bot_id": bot.bot_id,
        "title": bot.title,
        "username": bot.username,
        "token": bot.token,
        "is_enabled": bot.is_enabled,

        # inline MerchantConfig
        "merchant_config-0-id": str(mc.id),
        "merchant_config-0-merchant_account": "new_account",
        "merchant_config-0-secret_key": "new_secret",
        "merchant_config-0-pay_url": "https://secure.wayforpay.com/pay",
        "merchant_config-0-api_url": "https://api.wayforpay.com/api",
        "merchant_config-0-verify_signature": "on",

        # management form
        "merchant_config-TOTAL_FORMS": "1",
        "merchant_config-INITIAL_FORMS": "1",
        "merchant_config-MIN_NUM_FORMS": "0",
        "merchant_config-MAX_NUM_FORMS": "1",

        "_save": "Save",
    }

    response = admin_client.post(url, data, follow=True)
    assert response.status_code == 200

    mc.refresh_from_db()
    assert mc.merchant_account == "new_account"
    assert mc.secret_key == "new_secret"
    assert mc.verify_signature is True


@pytest.mark.django_db
@pytest.mark.covers("A1.3")
def test_bot_token_field_masked_in_admin(admin_client):
    """A1.3: Поле token в админке скрыто под маской (password input)."""
    bot = Bot.objects.create(bot_id=300, title="Masked Bot", username="masked_bot", token="SECRET")

    url = reverse("admin:core_bot_change", args=[bot.id])
    response = admin_client.get(url)

    assert response.status_code == 200
    html = response.content.decode()

    # Проверяем, что input для token отрендерен как password
    assert 'name="token"' in html
    assert 'type="password"' in html


@pytest.mark.django_db
@pytest.mark.covers("A2.1")
def test_admin_start_bot_triggers_supervisorctl(monkeypatch, admin_client):
    """A2.1: Кнопка Start запускает процесс через supervisorctl"""
    bot = Bot.objects.create(bot_id=400, title="Start Bot", username="start_bot", token="XYZ")

    called = {}

    def fake_check_output(args, stderr=None):
        called["args"] = args
        return b"started"

    monkeypatch.setattr("core.admin.subprocess.check_output", fake_check_output)

    url = reverse("admin:core_bot_start", args=[bot.id])
    response = admin_client.post(url, follow=True)

    assert response.status_code == 200
    assert called["args"][0] == "supervisorctl"
    assert b"started"



@pytest.mark.django_db
@pytest.mark.covers("A2.2")
def test_admin_stop_bot_triggers_supervisorctl(monkeypatch, admin_client):
    """A2.2: Кнопка Stop останавливает процесс через supervisorctl"""
    bot = Bot.objects.create(bot_id=401, title="Stop Bot", username="stop_bot", token="XYZ")

    called = {}
    def fake_check_output(args, stderr=None):
        called["args"] = args
        return b"stopped"

    monkeypatch.setattr("core.admin.subprocess.check_output", fake_check_output)

    url = reverse("admin:core_bot_stop", args=[bot.id])
    response = admin_client.post(url, follow=True)

    assert response.status_code == 200
    assert called["args"][1] == "stop"


@pytest.mark.django_db
@pytest.mark.covers("A2.3")
def test_admin_restart_bot_triggers_supervisorctl(monkeypatch, admin_client):
    """A2.3: Кнопка Restart перезапускает процесс через supervisorctl"""
    bot = Bot.objects.create(bot_id=402, title="Restart Bot", username="restart_bot", token="XYZ")

    called = {}
    def fake_check_output(args, stderr=None):
        called["args"] = args
        return b"restarted"

    monkeypatch.setattr("core.admin.subprocess.check_output", fake_check_output)

    url = reverse("admin:core_bot_restart", args=[bot.id])
    response = admin_client.post(url, follow=True)

    assert response.status_code == 200
    assert called["args"][1] == "restart"


@pytest.mark.django_db
@pytest.mark.covers("A2.4")
def test_admin_view_logs_shows_last_lines(tmp_path, admin_client):
    """A2.4: Кнопка View Logs показывает последние строки из log_path"""
    log_file = tmp_path / "bot.log"
    log_file.write_text("line1\nline2\nline3\n")

    bot = Bot.objects.create(
        bot_id=403, title="Log Bot", username="log_bot", token="XYZ", log_path=str(log_file)
    )

    url = reverse("admin:core_bot_logs", args=[bot.id])
    response = admin_client.get(url)

    assert response.status_code == 200
    html = response.content.decode()
    assert "line2" in html
    assert "line3" in html


@pytest.mark.django_db
@pytest.mark.covers("A2.5")
def test_admin_clear_logs_empties_file(tmp_path, admin_client):
    """A2.5: Кнопка Clear Logs очищает файл log_path"""
    log_file = tmp_path / "bot.log"
    log_file.write_text("old content\n")

    bot = Bot.objects.create(
        bot_id=404, title="Clear Bot", username="clear_bot", token="XYZ", log_path=str(log_file)
    )

    url = reverse("admin:core_bot_clear_logs", args=[bot.id])
    response = admin_client.post(url, follow=True)

    assert response.status_code == 200
    assert log_file.read_text() == ""
