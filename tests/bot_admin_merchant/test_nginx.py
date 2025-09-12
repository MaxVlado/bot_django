import pytest
from core.models import Bot
from botops import nginx

@pytest.mark.django_db
@pytest.mark.covers("A5.1")
def test_generate_nginx_location_for_bot():
    """A5.1: Генерация nginx location для бота (порт → /tg/bot-<id>/webhook)"""
    bot = Bot.objects.create(
        bot_id=700,
        title="NginxBot",
        username="nginx_bot",
        token="XYZ",
        port=8101
    )

    config = nginx.generate_location(bot)

    assert f"/tg/bot-{bot.bot_id}/webhook" in config
    assert f"127.0.0.1:{bot.port}" in config
