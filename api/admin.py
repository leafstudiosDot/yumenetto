

from django import forms
from django.contrib import admin
from django.contrib.admin import helpers
from django.shortcuts import render

# Set custom admin site titles
admin.site.site_header = 'YumeNetto Admin'
admin.site.site_title = 'YumeNetto'
admin.site.index_title = 'YumeNetto Administration'

from .models import Community
from .models import Thread
from .models import Reply

# Register your models here.

@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'title', 'description')

class StatusActionForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    status = forms.ChoiceField(choices=[
        ('public', 'Public'),
        ('platform_violation', 'Platform Rules Violation'),
        ('community_violation', 'Community Rules Violation'),
        ('removed_by_user', 'Removed by User'),
        ('removed_by_mod', 'Removed by Moderator'),
    ])
    removal_reason = forms.CharField(widget=forms.Textarea, required=False)

def set_status_with_reason(modeladmin, request, queryset):
    if 'apply' in request.POST:
        form = StatusActionForm(request.POST)
        if form.is_valid():
            status = form.cleaned_data['status']
            reason = form.cleaned_data['removal_reason']
            count = queryset.update(status=status, removal_reason=reason)
            modeladmin.message_user(request, f"Updated status for {count} items.")
            return None
    else:
        form = StatusActionForm(initial={'_selected_action': request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)})
    return render(request, 'admin/set_status_with_reason.html', {
        'items': queryset,
        'form': form,
        'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
    })
set_status_with_reason.short_description = "Set status and removal reason for selected items"

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ('title', 'community', 'author', 'created_at')
    list_filter = ('created_at', 'community')
    search_fields = ('title', 'description')
    actions = [set_status_with_reason]

@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ('thread', 'content', 'author', 'created_at', 'status')
    list_filter = ('created_at', 'status')
    search_fields = ('content',)
    actions = [set_status_with_reason]