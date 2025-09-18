# botops/supervisor.py
import subprocess
from pathlib import Path

SUPERVISOR_DIR = Path("/etc/supervisor/conf.d")


def generate_config(bot):
    return f"""
[program:bot-{bot.bot_id}]
command=/opt/venvs/dev-astrovoyager/bin/python /var/www/astrocryptov_usr/data/www/dev.astrocryptovoyager.com/bot_runner_aiogram.py --bot-id {bot.bot_id}
directory=/var/www/astrocryptov_usr/data/www/dev.astrocryptovoyager.com
autostart=true
autorestart=true
stderr_logfile={bot.log_path}
stdout_logfile={bot.log_path}
user=www-data
""".strip()


def write_config(bot):
    config_text = generate_config(bot)
    path = SUPERVISOR_DIR / f"bot-{bot.bot_id}.conf"
    path.write_text(config_text)
    return path


def _run(args):
    """Запуск supervisorctl (с sudo) и возврат stdout/stderr."""
    result = subprocess.run(args, capture_output=True, text=True)
    return (result.stdout or result.stderr).strip()


def get_status(bot):
    output = _run(["sudo", "supervisorctl", "status", f"bot-{bot.bot_id}"])
    if "RUNNING" in output:
        bot.status = "RUNNING"
    elif "STOPPED" in output:
        bot.status = "STOPPED"
    else:
        bot.status = "UNKNOWN"
    bot.save(update_fields=["status"])
    return bot.status


def start(bot):
    return _run(["sudo", "supervisorctl", "start", f"bot-{bot.bot_id}"])


def stop(bot):
    return _run(["sudo", "supervisorctl", "stop", f"bot-{bot.bot_id}"])


def restart(bot):
    return _run(["sudo", "supervisorctl", "restart", f"bot-{bot.bot_id}"])
