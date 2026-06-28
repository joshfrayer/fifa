from django.db import models


ROUND_SIZES = [16, 8, 4, 2, 1]
EMPTY_ROUNDS = [[None] * size for size in ROUND_SIZES]
DEFAULT_TEAMS = [
    "South Africa", "Canada", "Netherlands", "Morocco",
    "Germany", "Paraguay", "France", "Sweden",
    "Belgium", "Senegal", "United States", "Bosnia and Herzegovina",
    "Spain", "Austria", "Portugal", "Croatia",
    "Brazil", "Japan", "Ivory Coast", "Norway",
    "Mexico", "Ecuador", "England", "DR Congo",
    "Switzerland", "Algeria", "Colombia", "Ghana",
    "Argentina", "Cabo Verde", "Australia", "Eqypt",
]


def default_rounds():
    return [row[:] for row in EMPTY_ROUNDS]


def default_eligible_mask():
    return [[True] * size for size in ROUND_SIZES]


class Team(models.Model):
    name = models.CharField(max_length=80, unique=True)

    def __str__(self) -> str:
        return self.name


class Match(models.Model):
    round_index = models.PositiveSmallIntegerField()
    match_index = models.PositiveSmallIntegerField()
    home_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='home_matches',
    )
    away_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='away_matches',
    )
    winner = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='won_matches',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['round_index', 'match_index'], name='unique_round_match'),
        ]
        ordering = ['round_index', 'match_index']

    def __str__(self) -> str:
        return f'R{self.round_index + 1} M{self.match_index + 1}'

    @classmethod
    def rebuild_bracket(cls):
        matches = list(
            cls.objects.select_related('winner', 'home_team', 'away_team').order_by('round_index', 'match_index')
        )
        by_round = {round_index: [] for round_index in range(len(ROUND_SIZES))}
        for match in matches:
            by_round.setdefault(match.round_index, []).append(match)

        if any(len(by_round.get(round_index, [])) != ROUND_SIZES[round_index] for round_index in range(len(ROUND_SIZES))):
            return

        for round_index in range(1, len(ROUND_SIZES)):
            prev_round = by_round[round_index - 1]
            current_round = by_round[round_index]

            for idx, match in enumerate(current_round):
                expected_home = prev_round[idx * 2].winner
                expected_away = prev_round[idx * 2 + 1].winner
                valid_winner_ids = {team.id for team in (expected_home, expected_away) if team is not None}

                changed_fields = []
                if match.home_team_id != (expected_home.id if expected_home else None):
                    match.home_team = expected_home
                    changed_fields.append('home_team')
                if match.away_team_id != (expected_away.id if expected_away else None):
                    match.away_team = expected_away
                    changed_fields.append('away_team')

                if match.winner_id and match.winner_id not in valid_winner_ids:
                    match.winner = None
                    changed_fields.append('winner')

                if changed_fields:
                    match.save(skip_rebuild=True, update_fields=changed_fields)

    def save(self, *args, **kwargs):
        skip_rebuild = kwargs.pop('skip_rebuild', False)
        super().save(*args, **kwargs)
        if not skip_rebuild:
            Match.rebuild_bracket()


class BracketEntry(models.Model):
    name = models.CharField(max_length=80, unique=True)
    picks = models.JSONField(default=list)
    eligible_mask = models.JSONField(default=default_eligible_mask)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class TournamentResult(models.Model):
    slug = models.SlugField(unique=True, default="wc2026")
    rounds = models.JSONField(default=default_rounds)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.slug
