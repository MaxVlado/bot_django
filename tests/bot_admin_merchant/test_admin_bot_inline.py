import pytest
from django.urls import reverse
from core.models import Bot
from payments.models import MerchantConfig
from botops import supervisor


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
def test_admin_start_bot_triggers_supervisorctl(monkeypatch):
    called = {}

    def fake_run(args, capture_output=True, text=True):
        called["args"] = args
        class R:
            returncode = 0
            stdout = "bot_1: started"
            stderr = ""
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)

    bot = Bot.objects.create(bot_id=1, title="t", username="u", token="x")
    supervisor.start(bot)

    assert called["args"] == ["sudo", "supervisorctl", "start", f"bot_{bot.bot_id}"]


@pytest.mark.django_db
@pytest.mark.covers("A2.2")
def test_admin_stop_bot_triggers_supervisorctl(monkeypatch):
    called = {}
    def fake_run(args, capture_output=True, text=True):
        called["args"] = args
        class R: returncode, stdout, stderr = 0, "bot_1: stopped", ""
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)

    bot = Bot.objects.create(bot_id=1, title="t", username="u", token="x")
    supervisor.stop(bot)

    assert called["args"] == ["sudo", "supervisorctl", "stop", f"bot_{bot.bot_id}"]


@pytest.mark.django_db
@pytest.mark.covers("A2.3")
def test_admin_restart_bot_triggers_supervisorctl(monkeypatch):
    called = {}
    def fake_run(args, capture_output=True, text=True):
        called["args"] = args
        class R: returncode, stdout, stderr = 0, "bot_1: restarted", ""
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)

    bot = Bot.objects.create(bot_id=1, title="t", username="u", token="x")
    supervisor.restart(bot)

    assert called["args"] == ["sudo", "supervisorctl", "restart", f"bot_{bot.bot_id}"]

