from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='wc2026-bracket'),
]
