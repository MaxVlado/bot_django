from django.contrib import admin
from django.utils.html import format_html
from .models import TelegramUser, Bot
from payments.models import MerchantConfig


class MerchantConfigInline(admin.StackedInline):
    model = MerchantConfig
    can_delete = False
    extra = 0


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("bot_id", "username", "title", "is_enabled", "status", "port", "domain_name", "last_heartbeat")
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
