import pytest
import sys
from core.models import Bot
from payments.models import MerchantConfig
import bot_runner


@pytest.mark.django_db
@pytest.mark.covers("A4.1")
def test_bot_runner_loads_bot_and_merchant():
    """A4.1: bot_runner.py загружает конфиг Bot и MerchantConfig из БД"""
    bot = Bot.objects.create(bot_id=600, title="RunnerBot", username="runner_bot", token="XYZ")
    merchant = MerchantConfig.objects.create(bot=bot, merchant_account="acc", secret_key="key")

    loaded_bot, loaded_merchant = bot_runner.load_bot_config(bot.id)

    assert loaded_bot == bot
    assert loaded_merchant == merchant


@pytest.mark.django_db
@pytest.mark.covers("A4.2")
def test_bot_runner_exits_if_disabled(monkeypatch, capsys):
    """A4.2: bot_runner.py не запускает бота, если is_enabled=False"""
    bot = Bot.objects.create(bot_id=601, title="DisabledBot", username="disabled_bot", token="XYZ", is_enabled=False)

    monkeypatch.setattr(sys, "argv", ["bot_runner.py", "--bot-id", str(bot.id)])

    with pytest.raises(SystemExit) as e:
        bot_runner.main()

    captured = capsys.readouterr()
    assert "disabled" in captured.out.lower()
    assert e.value.code == 0

