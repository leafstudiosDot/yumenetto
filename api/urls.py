from django.urls import path
from . import views

from .views import ObtainJWTView, RegisterKeyView

urlpatterns = [
    path('index/', views.health_check, name='health-check'),
    path('pow-config/', views.pow_config, name='pow-config'),
    path('whoami/', views.whoami, name='whoami'),
    path('auth/login/', ObtainJWTView.as_view(), name='jwt-login'),
    path('auth/register/', RegisterKeyView.as_view(), name='jwt-register'),
    path('communities/', views.community_list, name='community-list'),
    path('communities/<str:name>/threads/', views.community_threads, name='community-threads'),
    path('communities/<str:name>/threads/<int:thread_id>/', views.thread_detail, name='thread-detail'),
]