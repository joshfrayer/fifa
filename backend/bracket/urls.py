from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='wc2026-bracket'),
    path('healthz/', views.healthz, name='wc2026-healthz'),
    path('leaderboard/', views.leaderboard_page, name='wc2026-leaderboard-page'),
    path('terms/', views.terms_page, name='wc2026-terms-page'),
    path('tv/', views.live_tv_player_page, name='wc2026-live-tv-player'),
    path('tv/live/proxy/', views.live_tv_stream_proxy, name='wc2026-live-tv-proxy'),
    path('tv/live/proxy/transcode/', views.live_tv_stream_transcode_proxy, name='wc2026-live-tv-proxy-transcode'),
    path('entry/<int:entry_id>/', views.entry_readonly, name='wc2026-entry-readonly'),
    path('api/submit-entry/', views.submit_entry, name='wc2026-submit-entry'),
    path('api/leaderboard/', views.leaderboard, name='wc2026-leaderboard'),
    path('api/entries/<int:entry_id>/', views.entry_detail, name='wc2026-entry-detail'),
    path('api/results/', views.get_results, name='wc2026-results-get'),
    path('api/results/set/', views.set_results, name='wc2026-results-set'),
]
