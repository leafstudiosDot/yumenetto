from django.contrib import admin

from .models import Community

# Register your models here.


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'title', 'description')
