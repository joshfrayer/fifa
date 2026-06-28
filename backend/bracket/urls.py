from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='wc2026-bracket'),
    path('api/submit-entry/', views.submit_entry, name='wc2026-submit-entry'),
    path('api/leaderboard/', views.leaderboard, name='wc2026-leaderboard'),
    path('api/results/', views.get_results, name='wc2026-results-get'),
    path('api/results/set/', views.set_results, name='wc2026-results-set'),
]
