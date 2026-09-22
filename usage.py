import csv
import io
import statistics
import time
from collections import defaultdict

import requests

from config import ESPN_SEASON


STATS_URL = (
    'https://github.com/nflverse/nflverse-data/releases/download/'
    'stats_player/stats_player_week_{season}.csv'
)
SNAPS_URL = (
    'https://github.com/nflverse/nflverse-data/releases/download/'
    'snap_counts/snap_counts_{season}.csv'
)

CACHE_SECONDS = 900
USAGE_CACHE = None
USAGE_CACHE_TIME = 0


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _first(row, *keys):
    for key in keys:
        if key in row and row.get(key) not in (None, ''):
            return row.get(key)
    return None


def _normalize_name(value):
    text = str(value or '').strip().lower()
    replacements = {
        '’': "'",
        '.': '',
        ',': '',
        '-': ' ',
        "'": '',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    suffixes = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}
    return ' '.join(
        part for part in text.split()
        if part not in suffixes
    )


def _position(row):
    return str(
        _first(row, 'position_group', 'position') or ''
    ).upper()


def _stat_value(row, *keys):
    return _num(_first(row, *keys))


def _download_csv(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = 'utf-8'
    return list(csv.DictReader(io.StringIO(response.text)))


def _load_raw_data():
    season = str(ESPN_SEASON or '2026')

    stats = _download_csv(STATS_URL.format(season=season))
    snaps = _download_csv(SNAPS_URL.format(season=season))

    return stats, snaps


def _team_snap_totals(snaps):
    """
    Infer the number of offensive snaps for each team/game from PFR's
    player-level snap counts.

    offense_pct is the player's percentage of the team's offensive snaps,
    so offense_snaps / offense_pct recovers the team total. We use the
    median of the available player-level estimates to avoid one unusual
    row dominating the result.
    """
    estimates = defaultdict(list)

    for row in snaps:
        team = str(row.get('team') or '').upper()
        week = int(_num(row.get('week')))
        game_type = str(row.get('game_type') or '').upper()
        if not team or not week or game_type not in {'REG', 'REGULAR'}:
            continue

        snaps_count = _stat_value(row, 'offense_snaps')
        pct = _stat_value(row, 'offense_pct')
        if snaps_count <= 0 or pct <= 0:
            continue

        if pct <= 1:
            pct *= 100

        if pct <= 0:
            continue

        estimates[(team, week)].append(
            snaps_count / (pct / 100.0)
        )

    totals = {}
    for key, values in estimates.items():
        if values:
            totals[key] = max(1.0, round(statistics.median(values)))

    return totals


def _build_weekly_records(stats, snaps):
    """
    Return normalized weekly player/team records.

    The player-stat release is the source for carries, targets and passing
    attempts. PFR snap counts are the source for offensive snap share.
    """
    snap_totals = _team_snap_totals(snaps)

    snap_players = {}
    for row in snaps:
        team = str(row.get('team') or '').upper()
        week = int(_num(row.get('week')))
        game_type = str(row.get('game_type') or '').upper()
        name = _normalize_name(row.get('player'))

        if (
            not team
            or not week
            or game_type not in {'REG', 'REGULAR'}
            or not name
        ):
            continue

        key = (team, week, name)
        existing = snap_players.setdefault(
            key,
            {
                'offense_snaps': 0.0,
                'offense_pct': None,
            },
        )

        existing['offense_snaps'] += _stat_value(
            row,
            'offense_snaps',
        )

        pct = _stat_value(row, 'offense_pct')
        if pct > 0:
            if pct <= 1:
                pct *= 100
            existing['offense_pct'] = pct

    player_week = defaultdict(
        lambda: {
            'name': '',
            'team': '',
            'position': '',
            'week': 0,
            'carries': 0.0,
            'targets': 0.0,
            'pass_attempts': 0.0,
            'sacks_suffered': 0.0,
        }
    )

    for row in stats:
        season_type = str(
            row.get('season_type') or ''
        ).upper()
        if season_type != 'REG':
            continue

        team = str(row.get('team') or '').upper()
        week = int(_num(row.get('week')))
        name = _normalize_name(
            _first(
                row,
                'player_display_name',
                'player_name',
            )
        )

        if not team or not week or not name:
            continue

        key = (team, week, name)
        record = player_week[key]

        record['name'] = (
            _first(
                row,
                'player_display_name',
                'player_name',
            )
            or record['name']
        )
        record['team'] = team
        record['position'] = _position(row) or record['position']
        record['week'] = week

        record['carries'] += _stat_value(
            row,
            'carries',
            'rushing_attempts',
            'rush_attempts',
        )
        record['targets'] += _stat_value(row, 'targets')

        if record['position'] == 'QB':
            record['pass_attempts'] += _stat_value(
                row,
                'attempts',
                'passing_attempts',
                'pass_attempts',
            )
            record['sacks_suffered'] += _stat_value(
                row,
                'sacks_suffered',
                'sacks',
            )

    # Add snap information and compute team-level totals.
    for key, record in player_week.items():
        team, week, name = key
        snap = snap_players.get(key, {})
        record['offense_snaps'] = _num(
            snap.get('offense_snaps')
        )
        record['team_offense_snaps'] = _num(
            snap_totals.get((team, week))
        )

    return list(player_week.values())


def _aggregate(records):
    grouped = defaultdict(
        lambda: {
            'name': '',
            'team': '',
            'position': '',
            'weeks': set(),
            'carries': 0.0,
            'targets': 0.0,
            'pass_attempts': 0.0,
            'sacks_suffered': 0.0,
            'offense_snaps': 0.0,
            'team_offense_snaps': 0.0,
        }
    )

    for row in records:
        key = (
            row['team'],
            _normalize_name(row['name']),
            row['position'],
        )
        out = grouped[key]
        out['name'] = row['name']
        out['team'] = row['team']
        out['position'] = row['position']
        out['weeks'].add(row['week'])

        for field in (
            'carries',
            'targets',
            'pass_attempts',
            'sacks_suffered',
            'offense_snaps',
            'team_offense_snaps',
        ):
            out[field] += row[field]

    return grouped


def _pct(numerator, denominator):
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _weekly_usage(records):
    by_week = defaultdict(list)
    for row in records:
        by_week[(row['team'], row['week'])].append(row)

    team_totals = {}
    for key, rows in by_week.items():
        team_totals[key] = {
            'rushes': sum(r['carries'] for r in rows),
            'targets': sum(r['targets'] for r in rows),
            'pass_attempts': sum(
                r['pass_attempts'] for r in rows
            ),
            'sacks': sum(
                r['sacks_suffered'] for r in rows
            ),
        }

    result = defaultdict(list)

    for (team, week), rows in by_week.items():
        totals = team_totals[(team, week)]
        pass_plays = (
            totals['pass_attempts']
            + totals['sacks']
        )
        total_plays = (
            totals['rushes']
            + pass_plays
        )

        run_pct = _pct(
            totals['rushes'],
            total_plays,
        )
        pass_pct = _pct(
            pass_plays,
            total_plays,
        )

        for row in rows:
            snap_share = _pct(
                row['offense_snaps'],
                row['team_offense_snaps'],
            )
            opportunity_rate = None
            if row['offense_snaps'] > 0:
                opportunity_rate = _pct(
                    row['carries'] + row['targets'],
                    row['offense_snaps'],
                )

            result[
                (
                    row['team'],
                    _normalize_name(row['name']),
                    row['position'],
                )
            ].append(
                {
                    'week': week,
                    'snap_share': snap_share,
                    'rush_share': _pct(
                        row['carries'],
                        totals['rushes'],
                    ),
                    'target_share': _pct(
                        row['targets'],
                        totals['targets'],
                    ),
                    'opportunity_rate': opportunity_rate,
                    'run_pct': run_pct,
                    'pass_pct': pass_pct,
                }
            )

    for values in result.values():
        values.sort(key=lambda item: item['week'])

    return result, team_totals


def _build_usage_data(records):
    weekly, team_totals = _weekly_usage(records)
    season = _aggregate(records)

    # Competition is calculated from season-to-date usage.
    rb_competition = defaultdict(list)
    target_competition = defaultdict(list)

    for key, row in season.items():
        team = row['team']
        position = row['position']

        if position == 'RB':
            rush_total = sum(
                value['carries']
                for other_key, value in season.items()
                if (
                    value['team'] == team
                    and value['position'] == 'RB'
                )
            )
            share = _pct(row['carries'], rush_total)
            if row['carries'] > 0:
                rb_competition[team].append(
                    {
                        'name': row['name'],
                        'position': position,
                        'share': share,
                    }
                )

        if position in {'RB', 'WR', 'TE'}:
            target_total = sum(
                value['targets']
                for other_key, value in season.items()
                if value['team'] == team
            )
            share = _pct(row['targets'], target_total)
            if row['targets'] > 0:
                target_competition[team].append(
                    {
                        'name': row['name'],
                        'position': position,
                        'share': share,
                    }
                )

    for values in rb_competition.values():
        values.sort(
            key=lambda item: item['share'] or 0,
            reverse=True,
        )

    for values in target_competition.values():
        values.sort(
            key=lambda item: item['share'] or 0,
            reverse=True,
        )

    players = {}

    for key, row in season.items():
        team = row['team']
        position = row['position']
        weekly_rows = weekly.get(key, [])

        current = weekly_rows[-1] if weekly_rows else {}

        if position == 'RB':
            rush_total = sum(
                value['carries']
                for value in season.values()
                if (
                    value['team'] == team
                    and value['position'] == 'RB'
                )
            )
            rush_share = _pct(
                row['carries'],
                rush_total,
            )
        else:
            rush_share = None

        if position in {'WR', 'TE'}:
            target_total = sum(
                value['targets']
                for value in season.values()
                if value['team'] == team
            )
            target_share = _pct(
                row['targets'],
                target_total,
            )
        else:
            target_share = None

        offense = {
            'run_pct': (
                current.get('run_pct')
                if current
                else None
            ),
            'pass_pct': (
                current.get('pass_pct')
                if current
                else None
            ),
        }

        # Season-to-date team tendency is more stable and is what the
        # main tray should display. The weekly value remains in history.
        team_weeks = [
            key[1]
            for key in team_totals
            if key[0] == team
        ]
        total_rushes = sum(
            team_totals[(team, week)]['rushes']
            for week in team_weeks
        )
        total_pass_plays = sum(
            team_totals[(team, week)]['pass_attempts']
            + team_totals[(team, week)]['sacks']
            for week in team_weeks
        )
        total_plays = total_rushes + total_pass_plays

        offense['run_pct'] = _pct(
            total_rushes,
            total_plays,
        )
        offense['pass_pct'] = _pct(
            total_pass_plays,
            total_plays,
        )

        season_snap_share = _pct(
            row['offense_snaps'],
            row['team_offense_snaps'],
        )

        season_opportunity = None
        if row['offense_snaps'] > 0:
            season_opportunity = _pct(
                row['carries'] + row['targets'],
                row['offense_snaps'],
            )

        usage = {
            'available': True,
            'position': position,
            'team': team,
            'snap_share': season_snap_share,
            'rush_share': rush_share,
            'target_share': target_share,
            'opportunity_rate': season_opportunity,
            'offense': offense,
            'competition': (
                rb_competition.get(team, [])
                if position == 'RB'
                else target_competition.get(team, [])
                if position in {'WR', 'TE'}
                else []
            )[:6],
            'weeks': weekly_rows,
        }

        players[(team, _normalize_name(row['name']), position)] = usage

    return players


def _empty_usage():
    return {
        'available': False,
        'position': None,
        'team': None,
        'snap_share': None,
        'rush_share': None,
        'target_share': None,
        'opportunity_rate': None,
        'offense': {
            'run_pct': None,
            'pass_pct': None,
        },
        'competition': [],
        'weeks': [],
    }


class UsageLookup:
    def __init__(self, players):
        self.players = players

    def get_usage(self, name, team, position):
        position = str(position or '').upper()
        team = str(team or '').upper()
        normalized = _normalize_name(name)

        if position not in {'RB', 'WR', 'TE'}:
            return _empty_usage()

        direct = self.players.get(
            (team, normalized, position)
        )
        if direct:
            return direct

        # Fallback for fantasy platforms that give a slightly different
        # position/name spelling. Team + normalized name is still required.
        for key, value in self.players.items():
            if (
                key[0] == team
                and key[1] == normalized
            ):
                return value

        return _empty_usage()


def build_usage_lookup():
    global USAGE_CACHE
    global USAGE_CACHE_TIME

    now = time.time()
    if (
        USAGE_CACHE is not None
        and now - USAGE_CACHE_TIME < CACHE_SECONDS
    ):
        return USAGE_CACHE

    try:
        stats, snaps = _load_raw_data()
        records = _build_weekly_records(stats, snaps)
        players = _build_usage_data(records)
        USAGE_CACHE = UsageLookup(players)
        USAGE_CACHE_TIME = now
        return USAGE_CACHE
    except Exception:
        # Do not take the fantasy dashboard down if nflverse is temporarily
        # unavailable. The next dashboard refresh will retry after the cache
        # remains empty.
        return UsageLookup({})
