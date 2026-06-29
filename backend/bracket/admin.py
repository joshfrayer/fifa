from django.contrib import admin

from .models import BracketEntry, Match, Team, TournamentResult


@admin.register(BracketEntry)
class BracketEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("round_index", "match_index", "kickoff_at", "home_team", "away_team", "winner")
    list_filter = ("round_index",)
    search_fields = ("home_team__name", "away_team__name", "winner__name")
    list_editable = ("kickoff_at", "winner")


@admin.register(TournamentResult)
class TournamentResultAdmin(admin.ModelAdmin):
    list_display = ("slug", "updated_at")
