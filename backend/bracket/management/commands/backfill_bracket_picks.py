from __future__ import annotations

from collections.abc import Iterable

from django.core.management.base import BaseCommand
from django.db import connection
from django.db import transaction

from bracket.models import BracketEntry, BracketPick, Match, ROUND_SIZES, Team


class Command(BaseCommand):
    help = "Backfill BracketPick rows from legacy BracketEntry JSON arrays."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entry-id",
            type=int,
            default=None,
            help="Backfill a single BracketEntry ID instead of all entries.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be written without modifying the database.",
        )

    def handle(self, *args, **options):
        entry_id: int | None = options["entry_id"]
        dry_run: bool = options["dry_run"]

        table_names = set(connection.introspection.table_names())
        if BracketPick._meta.db_table not in table_names:
            self.stdout.write(
                self.style.ERROR(
                    "BracketPick table is missing. Apply migrations first: "
                    "python manage.py migrate"
                )
            )
            return

        entries_qs = BracketEntry.objects.all().order_by("id")
        if entry_id is not None:
            entries_qs = entries_qs.filter(id=entry_id)

        entries = list(entries_qs)
        if not entries:
            self.stdout.write(self.style.WARNING("No matching BracketEntry rows found."))
            return

        match_by_key = {(m.round_index, m.match_index): m for m in Match.objects.all()}
        expected_match_count = sum(ROUND_SIZES)
        if len(match_by_key) != expected_match_count:
            self.stdout.write(
                self.style.ERROR(
                    f"Expected {expected_match_count} Match rows but found {len(match_by_key)}. "
                    "Initialize matches before running this command."
                )
            )
            return

        team_by_name = {team.name.casefold(): team for team in Team.objects.all()}

        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            for entry in entries:
                entry_created, entry_updated, entry_skipped = self._backfill_entry(
                    entry=entry,
                    match_by_key=match_by_key,
                    team_by_name=team_by_name,
                    dry_run=dry_run,
                )
                created += entry_created
                updated += entry_updated
                skipped += entry_skipped

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "Backfill complete. "
                f"entries={len(entries)} created={created} updated={updated} skipped={skipped} dry_run={dry_run}"
            )
        )

    def _backfill_entry(
        self,
        *,
        entry: BracketEntry,
        match_by_key: dict[tuple[int, int], Match],
        team_by_name: dict[str, Team],
        dry_run: bool,
    ) -> tuple[int, int, int]:
        picks = entry.picks
        eligible_mask = entry.eligible_mask

        if not _valid_rounds_shape(picks):
            self.stdout.write(
                self.style.WARNING(f"Entry {entry.id} skipped: invalid picks shape.")
            )
            return 0, 0, sum(ROUND_SIZES)

        if not _valid_rounds_shape(eligible_mask):
            eligible_mask = [[True] * size for size in ROUND_SIZES]

        created = 0
        updated = 0
        skipped = 0

        for round_index, size in enumerate(ROUND_SIZES):
            for match_index in range(size):
                match = match_by_key[(round_index, match_index)]
                pick_value = picks[round_index][match_index]
                team = _resolve_team(pick_value, team_by_name)
                is_eligible = bool(eligible_mask[round_index][match_index])

                defaults = {
                    "picked_team": team,
                    "is_eligible": is_eligible,
                    "picked_at": entry.created_at,
                }

                existing = BracketPick.objects.filter(entry=entry, match=match).first()
                if dry_run:
                    if existing is None:
                        created += 1
                    elif (
                        existing.picked_team_id != (team.id if team else None)
                        or existing.is_eligible != is_eligible
                        or existing.picked_at != entry.created_at
                    ):
                        updated += 1
                    else:
                        skipped += 1
                    continue

                if existing is None:
                    BracketPick.objects.create(
                        entry=entry,
                        match=match,
                        **defaults,
                    )
                    created += 1
                elif (
                    existing.picked_team_id == (team.id if team else None)
                    and existing.is_eligible == is_eligible
                    and existing.picked_at == entry.created_at
                ):
                    skipped += 1
                else:
                    existing.picked_team = team
                    existing.is_eligible = is_eligible
                    existing.picked_at = entry.created_at
                    existing.save(update_fields=["picked_team", "is_eligible", "picked_at"])
                    updated += 1

        return created, updated, skipped


def _resolve_team(name: str | None, team_by_name: dict[str, Team]) -> Team | None:
    if not name or name == "TBD":
        return None
    return team_by_name.get(str(name).casefold())


def _valid_rounds_shape(rows: object) -> bool:
    if not isinstance(rows, Iterable) or isinstance(rows, (str, bytes)):
        return False

    rows = list(rows)
    if len(rows) != len(ROUND_SIZES):
        return False

    for idx, size in enumerate(ROUND_SIZES):
        row = rows[idx]
        if not isinstance(row, Iterable) or isinstance(row, (str, bytes)):
            return False
        if len(list(row)) != size:
            return False

    return True

