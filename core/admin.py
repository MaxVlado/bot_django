from .models import TelegramUser, Bot
from payments.models import MerchantConfig
import subprocess
from django.urls import path
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404
from django.utils.html import format_html


class MerchantConfigInline(admin.StackedInline):
    model = MerchantConfig
    can_delete = False
    extra = 0


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("bot_id", "username", "title", "is_enabled", "status","port", "domain_name", "last_heartbeat", "action_buttons")
    search_fields = ("bot_id", "username", "title")
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
            '<a class="button" href="{}">Start</a>&nbsp;'
            '<a class="button" href="{}">Stop</a>&nbsp;'
            '<a class="button" href="{}">Restart</a>&nbsp;'
            '<a class="button" href="{}">Logs</a>&nbsp;'
            '<a class="button" href="{}">Clear Logs</a>',
            f"{obj.id}/start/",
            f"{obj.id}/stop/",
            f"{obj.id}/restart/",
            f"{obj.id}/logs/",
            f"{obj.id}/clear_logs/",
        )
    action_buttons.short_description = "Actions"
    action_buttons.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("<int:bot_id>/start/", self.admin_site.admin_view(self.start_bot), name="core_bot_start"),
            path("<int:bot_id>/stop/", self.admin_site.admin_view(self.stop_bot), name="core_bot_stop"),
            path("<int:bot_id>/restart/", self.admin_site.admin_view(self.restart_bot), name="core_bot_restart"),
            path("<int:bot_id>/logs/", self.admin_site.admin_view(self.view_logs), name="core_bot_logs"),
            path("<int:bot_id>/clear_logs/", self.admin_site.admin_view(self.clear_logs), name="core_bot_clear_logs"),
        ]
        return custom_urls + urls

    def supervisorctl(self, command, bot_id):
        program = f"bot-{bot_id}"
        return subprocess.check_output(["supervisorctl", command, program], stderr=subprocess.STDOUT)

    def start_bot(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, pk=bot_id)
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

    def view_logs(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, pk=bot_id)
        try:
            with open(bot.log_path, "r") as f:
                lines = f.readlines()[-50:]
            return HttpResponse("<br>".join(lines))
        except Exception as e:
            return HttpResponse(f"Error: {e}", status=500)

    def clear_logs(self, request, bot_id, *args, **kwargs):
        bot = get_object_or_404(Bot, pk=bot_id)
        try:
            open(bot.log_path, "w").close()
            self.message_user(request, "Logs cleared", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error: {e}", messages.ERROR)
        return HttpResponseRedirect(request.META.get("HTTP_REFERER"))


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
