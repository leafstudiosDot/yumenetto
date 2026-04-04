from django.contrib import admin

from .models import Community
from .models import Thread
from .models import Reply

# Register your models here.

@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'title', 'description')

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ('title', 'community', 'author', 'created_at')
    list_filter = ('created_at', 'community')
    search_fields = ('title', 'description')

@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ('thread', 'author', 'created_at', 'status')
    list_filter = ('created_at', 'status')
    search_fields = ('content',)