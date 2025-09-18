import pytest
from core.models import Bot
from botops import supervisor


@pytest.mark.django_db
@pytest.mark.covers("A3.1")
def test_generate_and_write_supervisor_config(tmp_path):
    """A3.1: Генерация supervisor-конфига для Bot корректна"""
    log_file = tmp_path / "bot_500.log"
    bot = Bot.objects.create(
        bot_id=500,
        title="Sup Bot",
        username="sup_bot",
        token="XYZ",
        log_path=str(log_file)
    )

    # Проверка генерации
    config_text = supervisor.generate_config(bot)
    assert f"[program:bot-{bot.bot_id}]" in config_text
    assert f"--bot-id {bot.bot_id}" in config_text
    assert bot.log_path in config_text

    # Проверка записи файла
    supervisor.SUPERVISOR_DIR = tmp_path
    path = supervisor.write_config(bot)
    assert path.exists()
    content = path.read_text()
    assert f"bot-{bot.bot_id}" in content
    assert bot.log_path in content


@pytest.mark.django_db
@pytest.mark.covers("A3.2")
def test_get_status_updates_bot_status(monkeypatch):
    """A3.2: Статус процесса синхронизируется в Bot.status"""
    bot = Bot.objects.create(
        bot_id=501,
        title="Stat Bot",
        username="stat_bot",
        token="XYZ",
    )

    class FakeCompleted:
        def __init__(self, stdout="bot-501    RUNNING   pid 1234, uptime 0:01:23"):
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, capture_output, text):
        return FakeCompleted()

    # патчим subprocess.run в модуле botops.supervisor
    monkeypatch.setattr("botops.supervisor.subprocess.run", fake_run)

    status = supervisor.get_status(bot)
    bot.refresh_from_db()

    assert status == "RUNNING"
    assert bot.status == "RUNNING"


