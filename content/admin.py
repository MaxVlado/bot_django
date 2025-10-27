# content/admin.py
from django.contrib import admin
from .models import (
    ContentTopic,
    TopicPlanAccess,
    Phase,
    ContentLesson,
    ContentPost,
    UserContentProgress
)


@admin.register(ContentTopic)
class ContentTopicAdmin(admin.ModelAdmin):
    list_display = ['id', 'sequence_number', 'title', 'bot', 'duration_days', 'enabled', 'created_at']
    list_filter = ['bot', 'enabled', 'sequence_number']
    search_fields = ['title', 'description']
    ordering = ['sequence_number', 'sort_order']
    list_editable = ['enabled']
    
    fieldsets = (
        ('Основное', {
            'fields': ('bot', 'title', 'description', 'sequence_number')
        }),
        ('Настройки', {
            'fields': ('duration_days', 'cover_image', 'enabled', 'sort_order')
        }),
    )


@admin.register(TopicPlanAccess)
class TopicPlanAccessAdmin(admin.ModelAdmin):
    list_display = ['id', 'plan', 'topic', 'month_number', 'enabled', 'sort_order']
    list_filter = ['plan', 'topic', 'month_number', 'enabled']
    ordering = ['plan', 'month_number', 'sort_order']
    list_editable = ['enabled']
    
    fieldsets = (
        (None, {
            'fields': ('plan', 'topic', 'month_number')
        }),
        ('Настройки', {
            'fields': ('enabled', 'sort_order')
        }),
    )


@admin.register(Phase)
class PhaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'slug', 'title', 'default_time', 'bot', 'sort_order']
    list_filter = ['bot']
    search_fields = ['slug', 'title']
    ordering = ['bot', 'sort_order', 'default_time']
    
    fieldsets = (
        (None, {
            'fields': ('bot', 'slug', 'title', 'default_time')
        }),
        ('Настройки', {
            'fields': ('sort_order',)
        }),
    )


class ContentPostInline(admin.TabularInline):
    model = ContentPost
    extra = 1
    fields = ['phase', 'title', 'content', 'media_file', 'send_time', 'enabled', 'sort_order']
    ordering = ['send_time', 'sort_order']


@admin.register(ContentLesson)
class ContentLessonAdmin(admin.ModelAdmin):
    list_display = ['id', 'topic', 'lesson_number', 'title', 'enabled', 'post_count']
    list_filter = ['topic', 'enabled']
    search_fields = ['title']
    ordering = ['topic', 'lesson_number']
    list_editable = ['enabled']
    
    inlines = [ContentPostInline]
    
    fieldsets = (
        (None, {
            'fields': ('topic', 'lesson_number', 'title', 'enabled')
        }),
    )
    
    def post_count(self, obj):
        return obj.posts.count()
    post_count.short_description = 'Постов'


@admin.register(ContentPost)
class ContentPostAdmin(admin.ModelAdmin):
    list_display = ['id', 'lesson', 'phase', 'title', 'post_type', 'send_time', 'enabled']
    list_filter = ['lesson__topic', 'phase', 'post_type', 'enabled', 'send_time']
    search_fields = ['title', 'content']
    ordering = ['lesson__lesson_number', 'send_time', 'sort_order']
    list_editable = ['enabled']
    
    readonly_fields = ['post_type', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Привязка', {
            'fields': ('lesson', 'phase')
        }),
        ('Контент', {
            'fields': ('title', 'content', 'media_file', 'post_type')
        }),
        ('Настройки', {
            'fields': ('send_time', 'enabled', 'sort_order')
        }),
        ('Служебное', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserContentProgress)
class UserContentProgressAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'topic', 'current_lesson_number', 
        'completed', 'started_at', 'last_sent_at'
    ]
    list_filter = ['topic', 'completed', 'started_at']
    search_fields = ['user__username', 'user__first_name', 'topic__title']
    ordering = ['-started_at']
    
    readonly_fields = ['created_at', 'updated_at', 'completed_at']
    
    fieldsets = (
        ('Привязка', {
            'fields': ('user', 'topic', 'subscription')
        }),
        ('Прогресс', {
            'fields': ('current_lesson_number', 'last_post_sent', 'last_sent_at')
        }),
        ('Статус', {
            'fields': ('started_at', 'completed', 'completed_at')
        }),
        ('Служебное', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )