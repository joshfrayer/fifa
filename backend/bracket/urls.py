from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='wc2026-bracket'),
    path('leaderboard/', views.leaderboard_page, name='wc2026-leaderboard-page'),
    path('tv/', views.channel_41_player_page, name='wc2026-channel-41-player'),
    path('tv/channel-4-1/proxy/', views.channel_41_stream_proxy, name='wc2026-channel-41-proxy'),
    path('tv/channel-4-1/proxy/transcode/', views.channel_41_stream_transcode_proxy, name='wc2026-channel-41-proxy-transcode'),
    path('entry/<int:entry_id>/', views.entry_readonly, name='wc2026-entry-readonly'),
    path('api/submit-entry/', views.submit_entry, name='wc2026-submit-entry'),
    path('api/leaderboard/', views.leaderboard, name='wc2026-leaderboard'),
    path('api/entries/<int:entry_id>/', views.entry_detail, name='wc2026-entry-detail'),
    path('api/results/', views.get_results, name='wc2026-results-get'),
    path('api/results/set/', views.set_results, name='wc2026-results-set'),
]
