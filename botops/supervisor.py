import subprocess
from pathlib import Path
from core.models import Bot

# По умолчанию supervisor конфиги лежат здесь,
# но в тестах мы будем подменять SUPERVISOR_DIR на tmp_path
SUPERVISOR_DIR = Path("/etc/supervisor/conf.d")


def generate_config(bot: Bot) -> str:
    """Генерирует текст supervisor-конфига для данного бота"""
    return f"""[program:bot-{bot.bot_id}]
command=/opt/venvs/bots/bin/python /path/to/bot_runner.py --bot-id {bot.bot_id}
directory=/var/www/astrocryptov_usr/data/www/dev.astrocryptovoyager.com
autostart=false
autorestart=true
stderr_logfile={bot.log_path}.err.log
stdout_logfile={bot.log_path}.out.log
"""


def write_config(bot: Bot) -> Path:
    """Сохраняет конфиг в файл supervisor"""
    config_text = generate_config(bot)
    path = SUPERVISOR_DIR / f"bot_{bot.bot_id}.conf"
    path.write_text(config_text)
    return path


def get_status(bot: Bot) -> str:
    """Запрашивает статус процесса у supervisorctl и обновляет bot.status"""
    try:
        output = subprocess.check_output(["supervisorctl", "status", f"bot-{bot.bot_id}"])
        status = output.decode().split()[1]  # RUNNING / STOPPED / STARTING и т.д.
        bot.status = status
        bot.save(update_fields=["status"])
        return status
    except Exception:
        bot.status = "failed"
        bot.save(update_fields=["status"])
        return "failed"
