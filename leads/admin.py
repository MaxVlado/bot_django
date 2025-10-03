# leads/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Q
from .models import LeadBotConfig, Lead


class LeadStatusFilter(admin.SimpleListFilter):
    """Фильтр по статусу заявки"""
    title = 'Статус заявки'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return Lead.STATUS_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class NotificationSentFilter(admin.SimpleListFilter):
    """Фильтр по отправке уведомлений"""
    title = 'Уведомления отправлены'
    parameter_name = 'notifications'

    def lookups(self, request, model_admin):
        return [
            ('all_sent', 'Все отправлены'),
            ('email_sent', 'Email отправлен'),
            ('telegram_sent', 'Telegram отправлен'),
            ('not_sent', 'Не отправлены'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'all_sent':
            return queryset.filter(email_sent=True, telegram_sent=True)
        elif self.value() == 'email_sent':
            return queryset.filter(email_sent=True)
        elif self.value() == 'telegram_sent':
            return queryset.filter(telegram_sent=True)
        elif self.value() == 'not_sent':
            return queryset.filter(email_sent=False, telegram_sent=False)
        return queryset


@admin.register(LeadBotConfig)
class LeadBotConfigAdmin(admin.ModelAdmin):
    """
    Админка для настроек Lead Bot.
    Доступ контролируется через permissions.
    """
    list_display = ('bot', 'notification_email', 'admin_user_id', 'created_at')
    search_fields = ('bot__username', 'notification_email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Основные настройки', {
            'fields': ('bot', 'notification_email', 'admin_user_id')
        }),
        ('Тексты бота', {
            'fields': (
                'welcome_text',
                'phone_request_text',
                'email_request_text',
                'comment_request_text',
                'success_text'
            ),
            'classes': ('collapse',)
        }),
        ('Метки времени', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_module_permission(self, request):
        """Показывать раздел только пользователям с правами"""
        return (
            request.user.is_superuser or
            request.user.has_perm('leads.can_manage_lead_bot') or
            request.user.has_perm('leads.can_view_leads')
        )
    
    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            request.user.has_perm('leads.can_manage_lead_bot')
        )
    
    def has_add_permission(self, request):
        return (
            request.user.is_superuser or
            request.user.has_perm('leads.can_manage_lead_bot')
        )
    
    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            request.user.has_perm('leads.can_manage_lead_bot')
        )
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    """
    Админка для просмотра и управления заявками.
    Доступ контролируется через permissions.
    """
    list_display = (
        'id',
        'full_name',
        'phone',
        'email',
        'status_badge',
        'bot',
        'notification_status',
        'created_at'
    )
    
    list_filter = (
        LeadStatusFilter,
        NotificationSentFilter,
        'bot',
        'created_at'
    )
    
    search_fields = (
        'full_name',
        'phone',
        'email',
        'user__username',
        'user__user_id',
        'comment'
    )
    
    readonly_fields = (
        'bot',
        'user',
        'created_at',
        'updated_at',
        'email_sent',
        'telegram_sent'
    )
    
    fieldsets = (
        ('Информация о заявке', {
            'fields': ('bot', 'user', 'status')
        }),
        ('Данные клиента', {
            'fields': ('full_name', 'phone', 'email', 'comment')
        }),
        ('Статус уведомлений', {
            'fields': ('email_sent', 'telegram_sent'),
            'classes': ('collapse',)
        }),
        ('Метки времени', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    def status_badge(self, obj):
        """Цветная метка статуса"""
        colors = {
            'new': '#FFA500',  # Оранжевый
            'in_progress': '#1E90FF',  # Синий
            'completed': '#28A745',  # Зеленый
            'cancelled': '#DC3545',  # Красный
        }
        color = colors.get(obj.status, '#6C757D')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Статус'
    
    def notification_status(self, obj):
        """Статус отправки уведомлений"""
        email_icon = '📧' if obj.email_sent else '❌'
        telegram_icon = '✅' if obj.telegram_sent else '❌'
        return format_html('{} {}', email_icon, telegram_icon)
    notification_status.short_description = 'Уведомления (📧/TG)'
    
    def has_module_permission(self, request):
        """Показывать раздел только пользователям с правами"""
        return (
            request.user.is_superuser or
            request.user.has_perm('leads.can_view_leads') or
            request.user.has_perm('leads.can_manage_lead_bot')
        )
    
    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            request.user.has_perm('leads.can_view_leads')
        )
    
    def has_add_permission(self, request):
        # Заявки создаются только через бота
        return False
    
    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser or
            request.user.has_perm('leads.can_view_leads')
        )
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def get_queryset(self, request):
        """Оптимизация запросов"""
        qs = super().get_queryset(request)
        return qs.select_related('bot', 'user')
