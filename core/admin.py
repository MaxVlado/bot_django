from django.contrib import admin
from .models import TelegramUser, Bot

admin.site.site_header = 'Админка ботов'

@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("bot_id", "username", "title", "is_enabled", "created_at")
    search_fields = ("bot_id", "username", "title")
    list_filter = ("is_enabled",)


from django.contrib import admin
from .models import TelegramUser


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
