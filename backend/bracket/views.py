import json
import os

from django.db import transaction
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import BracketEntry, DEFAULT_TEAMS, Match, Team, TournamentResult


ROUND_SIZES = [16, 8, 4, 2, 1]
ROUND_POINTS = [1, 2, 4, 8, 16]


def _empty_rounds() -> list[list[str | None]]:
    return [[None] * size for size in ROUND_SIZES]


def _empty_kickoff_rounds() -> list[list[str | None]]:
    return [[None] * size for size in ROUND_SIZES]


def _default_eligible_mask() -> list[list[bool]]:
    return [[True] * size for size in ROUND_SIZES]


def _default_locked_rounds() -> list[list[bool]]:
    return [[False] * size for size in ROUND_SIZES]


def _normalize_pick(value):
    if value in (None, "", "TBD"):
        return None
    if isinstance(value, str):
        return value
    return None


def _validate_rounds(rounds):
    if not isinstance(rounds, list) or len(rounds) != len(ROUND_SIZES):
        return False

    for idx, size in enumerate(ROUND_SIZES):
        if not isinstance(rounds[idx], list) or len(rounds[idx]) != size:
            return False
    return True


def _sanitize_rounds(rounds):
    return [[_normalize_pick(pick) for pick in row] for row in rounds]


def _validate_mask(mask):
    if not isinstance(mask, list) or len(mask) != len(ROUND_SIZES):
        return False

    for idx, size in enumerate(ROUND_SIZES):
        if not isinstance(mask[idx], list) or len(mask[idx]) != size:
            return False
        if not all(isinstance(value, bool) for value in mask[idx]):
            return False
    return True


def _is_complete(rounds):
    return all(all(pick for pick in row) for row in rounds)


def _score_entry(picks, results, eligible_mask):
    score = 0
    possible_scored = 0

    for round_index, points in enumerate(ROUND_POINTS):
        for match_index, winner in enumerate(results[round_index]):
            is_eligible = eligible_mask[round_index][match_index]
            if winner and is_eligible:
                possible_scored += points
                if picks[round_index][match_index] == winner:
                    score += points

    return score, possible_scored


def _results_instance() -> TournamentResult:
    result, _ = TournamentResult.objects.get_or_create(slug="wc2026", defaults={"rounds": _empty_rounds()})
    return result


def _official_rounds_from_matches():
    rounds = _empty_rounds()
    for match in Match.objects.select_related("winner").all():
        if match.round_index < len(ROUND_SIZES) and match.match_index < ROUND_SIZES[match.round_index]:
            rounds[match.round_index][match.match_index] = match.winner.name if match.winner else None
    return rounds


def _locked_rounds_from_matches(now=None):
    current_time = now or timezone.now()
    locked_rounds = _default_locked_rounds()

    for match in Match.objects.all().only('round_index', 'match_index', 'winner', 'kickoff_at'):
        if match.round_index < len(ROUND_SIZES) and match.match_index < ROUND_SIZES[match.round_index]:
            has_started = match.kickoff_at is not None and match.kickoff_at <= current_time
            locked_rounds[match.round_index][match.match_index] = bool(match.winner_id) or has_started

    return locked_rounds


@ensure_csrf_cookie
def index(request):
    teams = []
    kickoff_rounds = _empty_kickoff_rounds()
    locked_rounds = _locked_rounds_from_matches()

    for match in Match.objects.all().only('round_index', 'match_index', 'kickoff_at'):
        if match.round_index < len(ROUND_SIZES) and match.match_index < ROUND_SIZES[match.round_index]:
            kickoff_rounds[match.round_index][match.match_index] = (
                match.kickoff_at.isoformat() if match.kickoff_at else None
            )

    round32_matches = list(
        Match.objects.filter(round_index=0).select_related('home_team', 'away_team').order_by('match_index')
    )

    if len(round32_matches) == ROUND_SIZES[0]:
        for match in round32_matches:
            teams.append(match.home_team.name if match.home_team else 'TBD')
            teams.append(match.away_team.name if match.away_team else 'TBD')
    else:
        teams = list(DEFAULT_TEAMS)

    return render(
        request,
        'bracket/index.html',
        {
            'teams': teams,
            'kickoff_rounds': kickoff_rounds,
            'locked_rounds': locked_rounds,
        },
    )


@require_GET
def leaderboard_page(request: HttpRequest):
    return render(request, 'bracket/leaderboard.html')


@require_POST
@csrf_exempt
def submit_entry(request: HttpRequest):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    name = (payload.get("name") or "").strip()
    rounds = payload.get("rounds")

    if not name:
        return JsonResponse({"ok": False, "error": "Name is required."}, status=400)
    if len(name) > 80:
        return JsonResponse({"ok": False, "error": "Name is too long."}, status=400)
    if not _validate_rounds(rounds):
        return JsonResponse({"ok": False, "error": "Bracket data is invalid."}, status=400)

    rounds = _sanitize_rounds(rounds)

    official_rounds = _official_rounds_from_matches()
    locked_rounds = _locked_rounds_from_matches()
    eligible_mask = _default_eligible_mask()
    for round_index, row in enumerate(locked_rounds):
        for match_index, is_locked in enumerate(row):
            if is_locked:
                eligible_mask[round_index][match_index] = False
                winner = official_rounds[round_index][match_index]
                if winner:
                    rounds[round_index][match_index] = winner

    if not _is_complete(rounds):
        return JsonResponse({"ok": False, "error": "Complete all picks before submitting."}, status=400)

    if BracketEntry.objects.filter(name__iexact=name).exists():
        return JsonResponse({"ok": False, "error": "That name already has a submitted bracket."}, status=400)

    BracketEntry.objects.create(name=name, picks=rounds, eligible_mask=eligible_mask)
    return JsonResponse({"ok": True})


@require_GET
def leaderboard(request: HttpRequest):
    results = _official_rounds_from_matches()

    rows = []
    for entry in BracketEntry.objects.order_by("created_at"):
        if not _validate_rounds(entry.picks):
            continue

        eligible_mask = entry.eligible_mask
        if not _validate_mask(eligible_mask):
            eligible_mask = _default_eligible_mask()

        score, possible = _score_entry(entry.picks, results, eligible_mask)
        rows.append(
            {
                "id": entry.id,
                "name": entry.name,
                "score": score,
                "possible": possible,
                "submitted_at": entry.created_at.isoformat(),
            }
        )

    rows.sort(key=lambda item: (-item["score"], item["submitted_at"], item["name"].lower()))
    return JsonResponse({"ok": True, "rows": rows})


@require_GET
def entry_detail(request: HttpRequest, entry_id: int):
    try:
        entry = BracketEntry.objects.get(pk=entry_id)
    except BracketEntry.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Bracket entry not found."}, status=404)

    if not _validate_rounds(entry.picks):
        return JsonResponse({"ok": False, "error": "Stored bracket format is invalid."}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "entry": {
                "id": entry.id,
                "name": entry.name,
                "rounds": entry.picks,
                "submitted_at": entry.created_at.isoformat(),
            },
        }
    )


@require_GET
def entry_readonly(request: HttpRequest, entry_id: int):
    try:
        entry = BracketEntry.objects.get(pk=entry_id)
    except BracketEntry.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Bracket entry not found."}, status=404)

    if not _validate_rounds(entry.picks):
        return JsonResponse({"ok": False, "error": "Stored bracket format is invalid."}, status=400)

    initial_teams = []
    round32_matches = list(
        Match.objects.filter(round_index=0).select_related('home_team', 'away_team').order_by('match_index')
    )

    if len(round32_matches) == ROUND_SIZES[0]:
        for match in round32_matches:
            initial_teams.append(match.home_team.name if match.home_team else 'TBD')
            initial_teams.append(match.away_team.name if match.away_team else 'TBD')
    else:
        initial_teams = list(DEFAULT_TEAMS)

    return render(
        request,
        'bracket/entry_readonly.html',
        {
            'entry': entry,
            'initial_teams': initial_teams,
        },
    )


@require_GET
def get_results(request: HttpRequest):
    rounds = _official_rounds_from_matches()
    locked_rounds = _locked_rounds_from_matches()
    result = _results_instance()
    return JsonResponse(
        {
            "ok": True,
            "rounds": rounds,
            "locked_rounds": locked_rounds,
            "updated_at": result.updated_at.isoformat(),
        }
    )


@require_POST
def set_results(request: HttpRequest):
    admin_code = os.getenv("BRACKET_ADMIN_CODE", "change-me")

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    provided_code = (payload.get("admin_code") or "").strip()
    rounds = payload.get("rounds")

    if provided_code != admin_code:
        return JsonResponse({"ok": False, "error": "Admin code is invalid."}, status=403)
    if not _validate_rounds(rounds):
        return JsonResponse({"ok": False, "error": "Results payload is invalid."}, status=400)

    rounds = _sanitize_rounds(rounds)

    matches = {
        (match.round_index, match.match_index): match
        for match in Match.objects.select_related("home_team", "away_team").all()
    }

    if len(matches) != sum(ROUND_SIZES):
        return JsonResponse({"ok": False, "error": "Matches are not initialized in DB."}, status=400)

    team_by_name = {team.name.lower(): team for team in Team.objects.all()}

    with transaction.atomic():
        for round_index, row in enumerate(rounds):
            for match_index, winner_name in enumerate(row):
                match = matches[(round_index, match_index)]
                if winner_name is None:
                    match.winner = None
                    match.save(skip_rebuild=True, update_fields=["winner"])
                    continue

                team = team_by_name.get(winner_name.lower())
                if team is None:
                    return JsonResponse(
                        {"ok": False, "error": f"Unknown team in results: {winner_name}"}, status=400
                    )

                valid_ids = {team_id for team_id in (match.home_team_id, match.away_team_id) if team_id}
                if valid_ids and team.id not in valid_ids:
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": f"{winner_name} is not a valid winner for round {round_index + 1}, match {match_index + 1}.",
                        },
                        status=400,
                    )

                match.winner = team
                match.save(skip_rebuild=True, update_fields=["winner"])

        Match.rebuild_bracket()

    result = _results_instance()
    result.rounds = _official_rounds_from_matches()
    result.save(update_fields=["rounds", "updated_at"])
    return JsonResponse({"ok": True, "updated_at": result.updated_at.isoformat()})
