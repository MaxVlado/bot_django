import sys
import os
from pathlib import Path

import django
from fastapi import FastAPI
import uvicorn

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "profiling.settings")
django.setup()

from core.models import Bot
from payments.models import MerchantConfig


app = FastAPI()
BOT = None


def load_bot_config(bot_id: int):
    bot = Bot.objects.get(pk=bot_id)
    merchant = getattr(bot, "merchant_config", None)
    return bot, merchant


@app.post("/webhook")
async def webhook():
    log_file = Path(BOT.log_path)
    with open(log_file, "a") as f:
        f.write("webhook called\n")
    return {"ok": True}


def run_webhook(bot):
    global BOT
    BOT = bot
    uvicorn.run(app, host="127.0.0.1", port=bot.port)


def main():
    if "--bot-id" not in sys.argv:
        print("Usage: bot_runner.py --bot-id <id>")
        sys.exit(1)

    bot_id = int(sys.argv[sys.argv.index("--bot-id") + 1])
    bot, merchant = load_bot_config(bot_id)

    if not bot.is_enabled:
        print(f"Bot {bot_id} is disabled.")
        sys.exit(0)

    print(f"Running bot {bot_id} @{bot.username}")
    run_webhook(bot)


if __name__ == "__main__":
    main()
