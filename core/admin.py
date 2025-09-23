from .models import TelegramUser, Bot
from payments.models import MerchantConfig
import subprocess
from django.urls import path, reverse
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404
from django.utils.html import format_html
from django.conf import settings
from django.db import models




class MerchantConfigInline(admin.StackedInline):
    model = MerchantConfig
    can_delete = False
    extra = 0



@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("bot_id", "username", "is_enabled", "live_status","port",  "last_heartbeat", "action_buttons")
    search_fields = ("bot_id", "username")
    list_filter = ("is_enabled", "status")
    readonly_fields = ("status", "last_heartbeat")
    inlines = [MerchantConfigInline]

    fieldsets = (
        (None, {
            "fields": ("bot_id", "title", "username", "token", "is_enabled")
        }),
        ("Runtime", {
            "fields": ("port", "path", "log_path", "domain_name", "status", "last_heartbeat")
        }),
    )

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == "token":
            formfield.widget.attrs["type"] = "password"
        return formfield


    def action_buttons(self, obj):
        return format_html(
            '<div style="display: flex; flex-direction: column; gap: 4px;">'
            
            '    <a class="button" href="{}">Start</a>'
            '    <a class="button" href="{}">Stop</a>'
            '    <a class="button" href="{}">Restart</a><br>'

            '    <a class="button" href="{}">Restart Django</a><br>'

            '    <a class="button" href="{}">View Out Logs</a>'
            '    <a class="button" href="{}">View Err Logs</a><br>'
            '</div>',
            f"{obj.id}/start/",
            f"{obj.id}/stop/",
            f"{obj.id}/restart/",
            reverse("admin:core_restart_django"),
            f"{obj.id}/logs/out/",
            f"{obj.id}/logs/err/",            
        )
    
    
    action_buttons.short_description = "Actions"
    action_buttons.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("<int:bot_id>/start/", self.admin_site.admin_view(self.start_bot), name="core_bot_start"),
            path("<int:bot_id>/stop/", self.admin_site.admin_view(self.stop_bot), name="core_bot_stop"),
            path("<int:bot_id>/restart/", self.admin_site.admin_view(self.restart_bot), name="core_bot_restart"),
            path("<int:bot_id>/logs/out/", self.admin_site.admin_view(self.view_out_logs), name="core_bot_logs_out"),
            path("<int:bot_id>/logs/err/", self.admin_site.admin_view(self.view_err_logs), name="core_bot_logs_err"),
            path("restart_django/", self.admin_site.admin_view(self.restart_django), name="core_restart_django"),

        ]
        return custom_urls + urls

    def supervisorctl(self, command, bot_id):
        program = f"bot_{bot_id}"
        return subprocess.check_output(
            ["sudo",  "supervisorctl", command, program],
            stderr=subprocess.STDOUT
        )

    def start_bot(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, bot_id=bot_id)
        try:
            output = self.supervisorctl("start", bot.bot_id)
            self.message_user(request, f"Started: {output.decode()}", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error: {e}", messages.ERROR)
        return HttpResponseRedirect(request.META.get("HTTP_REFERER"))

    def stop_bot(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, pk=bot_id)
        try:
            output = self.supervisorctl("stop", bot.bot_id)
            self.message_user(request, f"Stopped: {output.decode()}", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error: {e}", messages.ERROR)
        return HttpResponseRedirect(request.META.get("HTTP_REFERER"))

    def restart_bot(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, pk=bot_id)
        try:
            output = self.supervisorctl("restart", bot.bot_id)
            self.message_user(request, f"Restarted: {output.decode()}", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error: {e}", messages.ERROR)
        return HttpResponseRedirect(request.META.get("HTTP_REFERER"))


    def live_status(self, obj):
        try:
            result = subprocess.run(
                ["sudo", "supervisorctl", "status", f"bot_{obj.bot_id}"],
                capture_output=True, text=True
            )
            output = result.stdout.strip()

            if "RUNNING" in output.upper():
                color, text = "green", "Running"
            elif "STOPPED" in output.upper():
                color, text = "red", "Stopped"
            elif "STARTING" in output.upper():
                color, text = "orange", "Starting"
            elif "EXITED" in output.upper():
                color, text = "gray", "Exited"
            elif "BACKOFF" in output.upper():
                color, text = "purple", "Backoff"
            elif "FATAL" in output.upper():
                color, text = "black", "Fatal"
            else:
                color, text = "gray", output or "Unknown"

        except Exception as e:
            color, text = "orange", f"Error: {e}"

        return format_html(
            '<span style="color: white; background-color: {}; padding: 2px 6px; border-radius: 4px;">{}</span>',
            color,
            text,
        )

    live_status.short_description = "Live Status"

    def restart_django(self, request):
        try:
            subprocess.run(
                ["sudo", "-n", "systemctl", "restart", "dev-astrovoyager"],
                capture_output=True, text=True
            )
            return HttpResponse(
                """
                <div style="text-align:center">
                <h2>Django service is restarting...</h2>
                <p>You will be redirected to the admin panel in <span id="counter">3</span> seconds.</p>
                </div>
                <script>
                    var count = 3;
                    var counterElem = document.getElementById("counter");
                    var interval = setInterval(function() {
                        count--;
                        if (count <= 0) {
                            clearInterval(interval);
                            window.location.href = '/admin/core/bot/';
                        } else {
                            counterElem.textContent = count;
                        }
                    }, 1000);
                </script>
                """,
                content_type="text/html"
            )
        except Exception as e:
            self.message_user(request, f"Error: {e}", messages.ERROR)
            return HttpResponseRedirect(request.META.get("HTTP_REFERER"))


    def view_out_logs(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, pk=bot_id)
        log_file = f"{bot.log_path}.out.log"
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()[-50:]
            return HttpResponse("<br>".join(lines))
        except Exception as e:
            return HttpResponse(f"Error: {e}", status=500)

    def view_err_logs(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, pk=bot_id)
        log_file = f"{bot.log_path}.err.log"
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()[-50:]
            return HttpResponse("<br>".join(lines))
        except Exception as e:
            return HttpResponse(f"Error: {e}", status=500)

    

class ActiveStatusFilter(admin.SimpleListFilter):
    title = "Active"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return (("1", "Active"), ("0", "Blocked"))

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(is_blocked=False)
        if self.value() == "0":
            return queryset.filter(is_blocked=True)
        return queryset


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ("user_id", "username", "first_name", "last_name", "is_active_badge", "created_at")
    search_fields = ("user_id", "username", "first_name", "last_name")
    list_filter = (ActiveStatusFilter, "created_at")
    ordering = ("-created_at",)

    def is_active_badge(self, obj):
        return not obj.is_blocked
    is_active_badge.boolean = True
    is_active_badge.short_description = "Is active"


#  Django log viewer

#  Django log viewer
from django.contrib import admin, messages
from django.urls import path, reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.conf import settings
from django.db import models

def _view_django_log(request):
    log_file = settings.LOG_DIR / "django.log"
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()[-200:]  # последние 200 строк
        # простая страница + быстрая ссылка на очистку
        clear_url = reverse("admin:core_clear_django_log")
        html = f'<p><a class="button" href="{clear_url}">Очистить лог</a></p>' + "<br>".join(lines)
        return HttpResponse(html)
    except Exception as e:
        return HttpResponse(f"Error: {e}", status=500)

def _clear_django_log(request):
    log_file = settings.LOG_DIR / "django.log"
    try:
        open(log_file, "w").close()
        messages.success(request, "Django log cleared")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return HttpResponseRedirect(reverse("admin:core_view_django_log"))

class LogDummy(models.Model):
    class Meta:
        managed = False
        app_label = "core"
        verbose_name = "Django Logs"
        verbose_name_plural = "Django Logs"

@admin.register(LogDummy)
class LogsAdmin(admin.ModelAdmin):
    """Пункт в главном меню админки без доступа к БД."""
    # запретим любые CRUD
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    # при клике по пункту меню сразу уводим на просмотр лога
    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse("admin:core_view_django_log"))

    # добавляем ровно два url: просмотр и очистка
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("django/", self.admin_site.admin_view(_view_django_log), name="core_view_django_log"),
            path("django/clear/", self.admin_site.admin_view(_clear_django_log), name="core_clear_django_log"),
        ]
        return custom + urls
