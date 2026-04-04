from django.urls import path
from . import views

from .views import ObtainJWTView, RegisterKeyView

urlpatterns = [
    path('index/', views.health_check, name='health-check'),
    path('pow-config/', views.pow_config, name='pow-config'),
    path('whoami/', views.whoami, name='whoami'),
    path('auth/login/', ObtainJWTView.as_view(), name='jwt-login'),
    path('auth/register/', RegisterKeyView.as_view(), name='jwt-register'),
]