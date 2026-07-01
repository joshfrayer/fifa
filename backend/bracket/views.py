import json
import os
import subprocess
import uuid
from ipaddress import ip_address
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.db import connection
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import BracketEntry, BracketPick, DEFAULT_TEAMS, Match, Team, TournamentResult


ROUND_SIZES = [16, 8, 4, 2, 1]
ROUND_POINTS = [1, 2, 4, 8, 16]
LIVE_TV_STREAM_LOCK_KEY = "bracket:live_tv:active_stream"
LIVE_TV_STREAM_LOCK_TTL_SECONDS = int((os.getenv("LIVE_TV_STREAM_LOCK_TTL", "75") or "75").strip())


def _acquire_live_tv_stream_lock() -> str | None:
    token = uuid.uuid4().hex
    acquired = cache.add(LIVE_TV_STREAM_LOCK_KEY, token, timeout=LIVE_TV_STREAM_LOCK_TTL_SECONDS)
    if not acquired:
        return None
    return token


def _refresh_live_tv_stream_lock(lock_token: str) -> None:
    current = cache.get(LIVE_TV_STREAM_LOCK_KEY)
    if current == lock_token:
        cache.set(LIVE_TV_STREAM_LOCK_KEY, lock_token, timeout=LIVE_TV_STREAM_LOCK_TTL_SECONDS)


def _release_live_tv_stream_lock(lock_token: str) -> None:
    current = cache.get(LIVE_TV_STREAM_LOCK_KEY)
    if current == lock_token:
        cache.delete(LIVE_TV_STREAM_LOCK_KEY)


def _empty_rounds() -> list[list[str | None]]:
    return [[None] * size for size in ROUND_SIZES]


def _empty_kickoff_rounds() -> list[list[str | None]]:
    return [[None] * size for size in ROUND_SIZES]


def _empty_score_rounds() -> list[list[dict[str, int | None]]]:
    return [[{"home": None, "away": None, "home_pk": None, "away_pk": None} for _ in range(size)] for size in ROUND_SIZES]


def _score_rounds_from_matches() -> list[list[dict[str, int | None]]]:
    score_rounds = _empty_score_rounds()
    for match in Match.objects.all().only('round_index', 'match_index', 'home_score', 'away_score', 'home_pk', 'away_pk'):
        if match.round_index < len(ROUND_SIZES) and match.match_index < ROUND_SIZES[match.round_index]:
            score_rounds[match.round_index][match.match_index] = {
                "home": match.home_score,
                "away": match.away_score,
                "home_pk": match.home_pk,
                "away_pk": match.away_pk,
            }
    return score_rounds


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


def _initial_teams_from_matches() -> list[str]:
    initial_teams = []
    round32_matches = list(
        Match.objects.filter(round_index=0).select_related('home_team', 'away_team').order_by('match_index')
    )

    if len(round32_matches) == ROUND_SIZES[0]:
        for match in round32_matches:
            initial_teams.append(match.home_team.name if match.home_team else 'TBD')
            initial_teams.append(match.away_team.name if match.away_team else 'TBD')
        return initial_teams

    return list(DEFAULT_TEAMS)


def _possible_winners_by_round(initial_teams: list[str], official_rounds: list[list[str | None]]) -> list[list[set[str]]]:
    possible: list[list[set[str]]] = [
        [set() for _ in range(size)] for size in ROUND_SIZES
    ]

    for match_index in range(ROUND_SIZES[0]):
        winner = official_rounds[0][match_index]
        if winner:
            possible[0][match_index] = {winner}
            continue

        home = initial_teams[match_index * 2] if match_index * 2 < len(initial_teams) else None
        away = initial_teams[match_index * 2 + 1] if (match_index * 2 + 1) < len(initial_teams) else None
        candidates = {team for team in (home, away) if team and team != 'TBD'}
        possible[0][match_index] = candidates

    for round_index in range(1, len(ROUND_SIZES)):
        for match_index in range(ROUND_SIZES[round_index]):
            winner = official_rounds[round_index][match_index]
            if winner:
                possible[round_index][match_index] = {winner}
                continue

            left_candidates = possible[round_index - 1][match_index * 2]
            right_candidates = possible[round_index - 1][match_index * 2 + 1]
            possible[round_index][match_index] = set(left_candidates) | set(right_candidates)

    return possible


def _max_possible_score(picks, results, eligible_mask, initial_teams):
    score, _ = _score_entry(picks, results, eligible_mask)
    possible_winners = _possible_winners_by_round(initial_teams, results)
    remaining_possible = 0

    for round_index, points in enumerate(ROUND_POINTS):
        for match_index, winner in enumerate(results[round_index]):
            if not eligible_mask[round_index][match_index]:
                continue

            if winner:
                continue

            pick = picks[round_index][match_index]
            if pick and pick in possible_winners[round_index][match_index]:
                remaining_possible += points

    return score + remaining_possible


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


def _bracket_pick_table_available() -> bool:
    table_names = set(connection.introspection.table_names())
    return BracketPick._meta.db_table in table_names


def _entry_rounds_and_mask_from_relational(entry: BracketEntry):
    if not _bracket_pick_table_available():
        return None

    picks = list(
        BracketPick.objects.filter(entry=entry)
        .select_related("match", "picked_team")
        .only("match__round_index", "match__match_index", "picked_team__name", "is_eligible")
    )

    if len(picks) != sum(ROUND_SIZES):
        return None

    rounds = _empty_rounds()
    eligible_mask = _default_eligible_mask()

    for pick in picks:
        round_index = pick.match.round_index
        match_index = pick.match.match_index
        if round_index >= len(ROUND_SIZES) or match_index >= ROUND_SIZES[round_index]:
            return None

        rounds[round_index][match_index] = pick.picked_team.name if pick.picked_team else None
        eligible_mask[round_index][match_index] = pick.is_eligible

    return rounds, eligible_mask


def _entry_rounds_and_mask(entry: BracketEntry):
    relational = _entry_rounds_and_mask_from_relational(entry)
    if relational is not None:
        return relational

    if not _validate_rounds(entry.picks):
        return None

    eligible_mask = entry.eligible_mask if _validate_mask(entry.eligible_mask) else _default_eligible_mask()
    return entry.picks, eligible_mask


def _sync_entry_picks(entry: BracketEntry, rounds, eligible_mask) -> None:
    if not _bracket_pick_table_available():
        return

    match_by_key = {(m.round_index, m.match_index): m for m in Match.objects.all()}
    if len(match_by_key) != sum(ROUND_SIZES):
        return

    team_by_name = {team.name.casefold(): team for team in Team.objects.all()}

    for round_index, size in enumerate(ROUND_SIZES):
        for match_index in range(size):
            team_name = rounds[round_index][match_index]
            team = team_by_name.get(str(team_name).casefold()) if team_name else None
            match = match_by_key[(round_index, match_index)]
            is_eligible = bool(eligible_mask[round_index][match_index])

            BracketPick.objects.update_or_create(
                entry=entry,
                match=match,
                defaults={
                    "picked_team": team,
                    "is_eligible": is_eligible,
                    "picked_at": entry.created_at,
                },
            )


@ensure_csrf_cookie
def index(request):
    teams = []
    kickoff_rounds = _empty_kickoff_rounds()
    score_rounds = _score_rounds_from_matches()
    locked_rounds = _locked_rounds_from_matches()

    for match in Match.objects.all().only('round_index', 'match_index', 'kickoff_at'):
        if match.round_index < len(ROUND_SIZES) and match.match_index < ROUND_SIZES[match.round_index]:
            kickoff_rounds[match.round_index][match.match_index] = (
                match.kickoff_at.isoformat() if match.kickoff_at else None
            )

    teams = _initial_teams_from_matches()

    return render(
        request,
        'bracket/index.html',
        {
            'teams': teams,
            'kickoff_rounds': kickoff_rounds,
            'score_rounds': score_rounds,
            'locked_rounds': locked_rounds,
        },
    )


@require_GET
def leaderboard_page(request: HttpRequest):
    return render(request, 'bracket/leaderboard.html')


@require_GET
def terms_page(request: HttpRequest):
    return render(request, 'bracket/terms.html')


@require_GET
def healthz(request: HttpRequest):
    return HttpResponse("ok", content_type="text/plain")


@require_GET
def live_tv_player_page(request: HttpRequest):
    default_stream_url = "http://10.45.67.62:5004/auto/v4.1"
    stream_url = (
        request.GET.get("src")
        or os.getenv("HDHR_LIVE_TV_URL", "")
        or default_stream_url
    ).strip()

    proxy_url = f"/tv/live/proxy/?src={quote(stream_url, safe='')}"
    transcode_proxy_url = f"/tv/live/proxy/transcode/?src={quote(stream_url, safe='')}"
    proxy_url_absolute = request.build_absolute_uri(proxy_url)
    transcode_proxy_url_absolute = request.build_absolute_uri(transcode_proxy_url)
    return render(
        request,
        'bracket/live_tv_player.html',
        {
            'stream_url': stream_url,
            'proxy_url': proxy_url,
            'proxy_url_absolute': proxy_url_absolute,
            'transcode_proxy_url': transcode_proxy_url,
            'transcode_proxy_url_absolute': transcode_proxy_url_absolute,
        },
    )


def _is_allowed_proxy_target(stream_url: str) -> bool:
    try:
        parsed = urlparse(stream_url)
    except Exception:
        return False

    if parsed.scheme != "http" or not parsed.hostname:
        return False

    host = parsed.hostname.strip().lower()
    if host == "localhost":
        return True

    try:
        host_ip = ip_address(host)
        return host_ip.is_private or host_ip.is_loopback
    except ValueError:
        # Allow mDNS/local hostnames.
        return host.endswith(".local")


@require_GET
def live_tv_stream_proxy(request: HttpRequest):
    default_stream_url = "http://10.45.67.62:5004/auto/v4.1"
    stream_url = (
        request.GET.get("src")
        or os.getenv("HDHR_LIVE_TV_URL", "")
        or default_stream_url
    ).strip()

    if not _is_allowed_proxy_target(stream_url):
        return JsonResponse({"ok": False, "error": "Proxy target is not allowed."}, status=400)

    lock_token = _acquire_live_tv_stream_lock()
    if lock_token is None:
        return JsonResponse(
            {"ok": False, "error": "Live TV is already in use. Only one stream is allowed at a time."},
            status=429,
        )

    upstream_request = Request(stream_url, headers={"User-Agent": "Django-HDHR-Proxy/1.0"})

    try:
        upstream_response = urlopen(upstream_request, timeout=8)
    except Exception as exc:
        _release_live_tv_stream_lock(lock_token)
        return JsonResponse({"ok": False, "error": f"Unable to open upstream stream: {exc}"}, status=502)

    content_type = upstream_response.headers.get("Content-Type", "video/mpeg")

    def stream_chunks():
        try:
            while True:
                chunk = upstream_response.read(64 * 1024)
                if not chunk:
                    break
                _refresh_live_tv_stream_lock(lock_token)
                yield chunk
        finally:
            upstream_response.close()
            _release_live_tv_stream_lock(lock_token)

    response = StreamingHttpResponse(stream_chunks(), content_type=content_type)
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@require_GET
def live_tv_stream_transcode_proxy(request: HttpRequest):
    default_stream_url = "http://10.45.67.62:5004/auto/v4.1"
    stream_url = (
        request.GET.get("src")
        or os.getenv("HDHR_LIVE_TV_URL", "")
        or default_stream_url
    ).strip()

    if not _is_allowed_proxy_target(stream_url):
        return JsonResponse({"ok": False, "error": "Proxy target is not allowed."}, status=400)

    lock_token = _acquire_live_tv_stream_lock()
    if lock_token is None:
        return JsonResponse(
            {"ok": False, "error": "Live TV is already in use. Only one stream is allowed at a time."},
            status=429,
        )

    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        ffmpeg_exe = get_ffmpeg_exe()
    except Exception as exc:
        _release_live_tv_stream_lock(lock_token)
        return JsonResponse({"ok": False, "error": f"FFmpeg runtime is unavailable: {exc}"}, status=500)

    # Tune for smoother browser playback on constrained LAN/Wi-Fi clients.
    output_height = (os.getenv("HDHR_TRANSCODE_HEIGHT", "720") or "720").strip()
    output_fps = (os.getenv("HDHR_TRANSCODE_FPS", "30") or "30").strip()
    output_bitrate = (os.getenv("HDHR_TRANSCODE_BITRATE", "2500k") or "2500k").strip()
    output_maxrate = (os.getenv("HDHR_TRANSCODE_MAXRATE", "3000k") or "3000k").strip()
    output_bufsize = (os.getenv("HDHR_TRANSCODE_BUFSIZE", "6000k") or "6000k").strip()
    enable_deinterlace = (os.getenv("HDHR_TRANSCODE_DEINTERLACE", "1") or "1").strip().lower() in {"1", "true", "yes", "on"}

    vf_filters = []
    if enable_deinterlace:
        vf_filters.append("yadif")
    vf_filters.append(f"scale=-2:{output_height}")
    vf_filters.append(f"fps={output_fps}")
    vf_value = ",".join(vf_filters)

    ffmpeg_cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-i",
        stream_url,
        "-vf",
        vf_value,
        "-an",
        "-sn",
        "-dn",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "zerolatency",
        "-r",
        output_fps,
        "-b:v",
        output_bitrate,
        "-maxrate",
        output_maxrate,
        "-bufsize",
        output_bufsize,
        "-g",
        "30",
        "-keyint_min",
        "30",
        "-x264-params",
        "scenecut=0",
        "-pix_fmt",
        "yuv420p",
        "-f",
        "mpegts",
        "pipe:1",
    ]

    try:
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except Exception as exc:
        _release_live_tv_stream_lock(lock_token)
        return JsonResponse({"ok": False, "error": f"Failed to start FFmpeg: {exc}"}, status=500)

    def stream_chunks():
        try:
            while True:
                if process.stdout is None:
                    break
                chunk = process.stdout.read(64 * 1024)
                if chunk:
                    _refresh_live_tv_stream_lock(lock_token)
                    yield chunk
                    continue

                if process.poll() is not None:
                    break
        finally:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=1)
            except Exception:
                pass
            _release_live_tv_stream_lock(lock_token)

    response = StreamingHttpResponse(stream_chunks(), content_type="video/mp2t")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


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

    with transaction.atomic():
        entry = BracketEntry.objects.create(name=name, picks=rounds, eligible_mask=eligible_mask)
        _sync_entry_picks(entry, rounds, eligible_mask)
    return JsonResponse({"ok": True})


@require_GET
def leaderboard(request: HttpRequest):
    results = _official_rounds_from_matches()
    initial_teams = _initial_teams_from_matches()

    rows = []
    for entry in BracketEntry.objects.order_by("created_at"):
        entry_data = _entry_rounds_and_mask(entry)
        if entry_data is None:
            continue

        entry_rounds, eligible_mask = entry_data

        score, _ = _score_entry(entry_rounds, results, eligible_mask)
        max_possible = _max_possible_score(entry_rounds, results, eligible_mask, initial_teams)
        rows.append(
            {
                "id": entry.id,
                "name": entry.name,
                "score": score,
                "possible": max_possible,
                "max_possible": max_possible,
                "submitted_at": entry.created_at.isoformat(),
            }
        )

    rows.sort(key=lambda item: (-item["score"], -item["max_possible"], item["submitted_at"], item["name"].lower()))
    return JsonResponse({"ok": True, "rows": rows})


@require_GET
def entry_detail(request: HttpRequest, entry_id: int):
    try:
        entry = BracketEntry.objects.get(pk=entry_id)
    except BracketEntry.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Bracket entry not found."}, status=404)

    entry_data = _entry_rounds_and_mask(entry)
    if entry_data is None:
        return JsonResponse({"ok": False, "error": "Stored bracket format is invalid."}, status=400)

    entry_rounds, _ = entry_data

    return JsonResponse(
        {
            "ok": True,
            "entry": {
                "id": entry.id,
                "name": entry.name,
                "rounds": entry_rounds,
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

    entry_data = _entry_rounds_and_mask(entry)
    if entry_data is None:
        return JsonResponse({"ok": False, "error": "Stored bracket format is invalid."}, status=400)

    entry_rounds, eligible_mask = entry_data

    initial_teams = _initial_teams_from_matches()
    official_rounds = _official_rounds_from_matches()
    kickoff_rounds = _empty_kickoff_rounds()
    score_rounds = _score_rounds_from_matches()
    for match in Match.objects.all().only('round_index', 'match_index', 'kickoff_at'):
        if match.round_index < len(ROUND_SIZES) and match.match_index < ROUND_SIZES[match.round_index]:
            kickoff_rounds[match.round_index][match.match_index] = (
                match.kickoff_at.isoformat() if match.kickoff_at else None
            )
    return render(
        request,
        'bracket/entry_readonly.html',
        {
            'entry': entry,
            'entry_rounds': entry_rounds,
            'initial_teams': initial_teams,
            'official_rounds': official_rounds,
            'kickoff_rounds': kickoff_rounds,
            'score_rounds': score_rounds,
            'eligible_mask': eligible_mask,
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
