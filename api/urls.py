from django.urls import path
from . import views

urlpatterns = [
    path('index/', views.health_check, name='health-check'),
    path('pow-config/', views.pow_config, name='pow-config'),
    path('whoami/', views.whoami, name='whoami'),
]