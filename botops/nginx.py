# botops/nginx.py
from core.models import Bot

def generate_location(bot: Bot) -> str:
    """
    Генерирует nginx location для данного бота:
    /tg/bot-<id>/webhook → 127.0.0.1:<port>/webhook
    """
    return f"""
location /tg/bot-{bot.bot_id}/webhook {{
    proxy_pass http://127.0.0.1:{bot.port}/webhook;
    proxy_set_header Host $host;
}}
""".strip()

def generate_location(bot: Bot) -> str:
    """
    Генерирует nginx location для данного бота:
    /tg/bot-<id>/webhook → 127.0.0.1:<port>/webhook
    """
    return f"""
location /tg/bot-{bot.bot_id}/webhook {{
    proxy_pass http://127.0.0.1:{bot.port}/webhook;
    proxy_set_header Host $host;
}}
""".strip()