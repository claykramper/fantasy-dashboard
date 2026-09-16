import requests
import time

from config import (
    SLEEPER_API_URL,
    SLEEPER_PROJECTIONS_URL,
    SLEEPER_STATS_URL,
    SLEEPER_USERNAME,
)


PLAYER_CACHE = None
PLAYER_CACHE_TIME = 0
PROJECTION_CACHE = {}
STATS_CACHE = {}


def get(path):
    response = requests.get(
        f'{SLEEPER_API_URL}{path}',
        timeout=20,
        headers={
            'User-Agent': (
                'Mozilla/5.0 '
                '(Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 '
                '(KHTML, like Gecko) '
                'Chrome/140.0 Safari/537.36'
            )
        },
    )
    response.raise_for_status()
    return response.json()


def sleeper_projection_request(url, params=None):
    response = requests.get(
        url,
        params=params or {},
        timeout=30,
        headers={
            'User-Agent': (
                'Mozilla/5.0 '
                '(Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 '
                '(KHTML, like Gecko) '
                'Chrome/140.0 Safari/537.36'
            ),
            'Accept': 'application/json,text/plain,*/*',
            'Referer': 'https://sleeper.com/',
        },
    )
    response.raise_for_status()
    return response.json()


def get_sleeper_user():
    return get(f'/user/{SLEEPER_USERNAME}')


def get_sleeper_leagues(user_id, season=2026):
    return get(
        f'/user/{user_id}/leagues/nfl/{season}'
    )


def get_sleeper_state():
    return get('/state/nfl')


def get_sleeper_league(league_id):
    return get(f'/league/{league_id}')


def get_sleeper_rosters(league_id):
    return get(f'/league/{league_id}/rosters')


def get_sleeper_users(league_id):
    return get(f'/league/{league_id}/users')


def get_sleeper_matchups(league_id, week):
    return get(
        f'/league/{league_id}/matchups/{week}'
    )


def get_sleeper_players():
    global PLAYER_CACHE
    global PLAYER_CACHE_TIME

    if (
        PLAYER_CACHE is not None
        and time.time() - PLAYER_CACHE_TIME < 86400
    ):
        return PLAYER_CACHE

    PLAYER_CACHE = get('/players/nfl')
    PLAYER_CACHE_TIME = time.time()

    return PLAYER_CACHE


def choose_league(leagues):
    if not leagues:
        raise RuntimeError(
            'No Sleeper NFL leagues found.'
        )

    return next(
        (
            league
            for league in leagues
            if league.get('status') == 'in_season'
        ),
        leagues[0],
    )


def num(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def rows(data):
    if isinstance(data, dict):
        return data

    if isinstance(data, list):
        return {
            str(item['player_id']): item
            for item in data
            if (
                isinstance(item, dict)
                and item.get('player_id') is not None
            )
        }

    return {}


def position(player):
    positions = player.get(
        'fantasy_positions'
    ) or []

    if positions:
        return positions[0]

    return player.get(
        'position',
        ''
    )


def points(
    stats,
    scoring,
    pos,
    allow_provider_fallback=False,
):
    if not isinstance(stats, dict):
        return None

    total = 0.0
    matched = False

    for key, value in scoring.items():
        if key in stats:
            matched = True

            total += (
                num(stats[key])
                * num(value)
            )

    bonus = {
        'RB': 'bonus_rec_rb',
        'WR': 'bonus_rec_wr',
        'TE': 'bonus_rec_te',
    }.get(
        str(pos).upper()
    )

    if (
        bonus
        and bonus in scoring
        and 'rec' in stats
    ):
        matched = True

        total += (
            num(stats.get('rec'))
            * num(scoring[bonus])
        )

    if (
        allow_provider_fallback
        and not matched
        and stats.get('pts_ppr') is not None
    ):
        return round(
            num(stats.get('pts_ppr')),
            2,
        )

    return round(
        total,
        2,
    )


def score(
    player_id,
    player,
    projections,
    actual,
    scoring,
):
    projection_row = rows(
        projections
    ).get(
        str(player_id)
    )

    actual_row = rows(
        actual
    ).get(
        str(player_id)
    )

    pos = position(player)

    projected = (
        points(
            projection_row,
            scoring,
            pos,
            allow_provider_fallback=True,
        )
        if projection_row
        else None
    )

    real = (
        points(
            actual_row,
            scoring,
            pos,
        )
        if (
            actual_row
            and num(
                actual_row.get('gp')
            ) > 0
        )
        else None
    )

    return projected, real


def game_info(team, lookup):
    game = lookup.get(
        str(team or '').upper()
    )

    if not game:
        return {
            'team': team or '',
            'opponent': '',
            'game_time': '',
            'game_status': '',
            'status_detail': '',
            'team_id': str(team or ''),
        }

    return {
        'team': game['team'],
        'opponent': game['opponent'],
        'game_time': game['game_time'],
        'game_status': game['game_status'],
        'status_detail': game.get(
            'status_detail',
            '',
        ),
        'team_id': game.get(
            'team_id',
            '',
        ),
    }


def build_players(
    player_ids,
    starter_ids,
    players,
    projections,
    actual,
    scoring,
    lookup,
):
    out = []

    starter_set = {
        str(player_id)
        for player_id in starter_ids
    }

    for player_id in player_ids:
        player = players.get(
            str(player_id)
        )

        if not player:
            continue

        projected, real = score(
            player_id,
            player,
            projections,
            actual,
            scoring,
        )

        team = player.get(
            'team'
        ) or ''

        game = game_info(
            team,
            lookup,
        )

        finished = (
            'FINAL'
            in str(
                game['game_status']
            ).upper()
        )

        is_starter = (
            str(player_id)
            in starter_set
        )

        name = (
            player.get('full_name')
            or ' '.join(
                part
                for part in [
                    player.get(
                        'first_name',
                        '',
                    ),
                    player.get(
                        'last_name',
                        '',
                    ),
                ]
                if part
            )
        )

        out.append({
            'name': name,
            'slot': (
                position(player)
                if is_starter
                else 'BN'
            ),
            'player_id': str(player_id),
            'nfl_team': game['team'],
            'opponent': game['opponent'],
            'game_time': game['game_time'],
            'game_status': game['game_status'],
            'status_detail': game.get(
                'status_detail',
                '',
            ),
            'points': (
                real
                if real is not None
                else projected
            ),
            'projected': projected,
            'actual': real,
            'injury': (
                player.get(
                    'injury_status'
                )
                or ''
            ),
            'status': (
                'LOCKED'
                if finished
                else (
                    'LIVE'
                    if real is not None
                    else 'PROJECTED'
                )
            ),
            'pro_team_id': team,
            'starter': is_starter,
            'bench': not is_starter,
        })

    return out


def tname(roster, users):
    metadata = roster.get(
        'metadata'
    ) or {}

    if metadata.get(
        'team_name'
    ):
        return metadata['team_name']

    for user in users:
        if (
            user.get('user_id')
            == roster.get('owner_id')
        ):
            return (
                user.get('display_name')
                or user.get('username')
                or f"Roster {roster.get('roster_id')}"
            )

    return f"Roster {roster.get('roster_id')}"


def get_week_data(
    season,
    week,
):
    cache_key = (
        int(season),
        int(week),
    )

    if cache_key not in PROJECTION_CACHE:
        projection_url = (
            f'{SLEEPER_PROJECTIONS_URL}/'
            f'{season}/{week}'
        )

        PROJECTION_CACHE[cache_key] = (
            time.time(),
            sleeper_projection_request(
                projection_url,
                params={
                    'season_type': 'regular',
                },
            ),
        )

    if cache_key not in STATS_CACHE:
        stats_url = (
            f'{SLEEPER_STATS_URL}/'
            f'regular/{season}/{week}'
        )

        STATS_CACHE[cache_key] = (
            time.time(),
            get(
                f'/stats/nfl/regular/{season}/{week}'
            ),
        )

    return (
        PROJECTION_CACHE[cache_key][1],
        STATS_CACHE[cache_key][1],
    )


def build_sleeper_matchup(lookup):
    user = get_sleeper_user()

    state = get_sleeper_state()

    season = int(
        state.get('season')
        or 2026
    )

    league_season = int(
        state.get('league_season')
        or season
    )

    leagues = get_sleeper_leagues(
        user['user_id'],
        league_season,
    )

    league = choose_league(
        leagues
    )

    league_id = league['league_id']

    league_data = get_sleeper_league(
        league_id
    )

    week = int(
        state.get('display_week')
        or state.get('week')
        or 1
    )

    rosters = get_sleeper_rosters(
        league_id
    )

    users = get_sleeper_users(
        league_id
    )

    matchups = get_sleeper_matchups(
        league_id,
        week,
    )

    if not matchups:
        backend_week = int(
            state.get('week')
            or week
        )

        if backend_week != week:
            week = backend_week

            matchups = get_sleeper_matchups(
                league_id,
                week,
            )

    if not matchups:
        raise RuntimeError(
            f'No Sleeper matchups found for week {week}.'
        )

    my_roster = next(
        roster
        for roster in rosters
        if roster.get('owner_id')
        == user['user_id']
    )

    my_matchup = next(
        matchup
        for matchup in matchups
        if matchup.get('roster_id')
        == my_roster['roster_id']
    )

    opponent_matchup = next(
        matchup
        for matchup in matchups
        if (
            matchup.get('matchup_id')
            == my_matchup.get('matchup_id')
            and matchup.get('roster_id')
            != my_roster['roster_id']
        )
    )

    opponent_roster = next(
        roster
        for roster in rosters
        if roster.get('roster_id')
        == opponent_matchup['roster_id']
    )

    players = get_sleeper_players()

    projections, actual = get_week_data(
        season,
        week,
    )

    scoring = (
        league_data.get(
            'scoring_settings'
        )
        or {}
    )

    my_player_ids = (
        my_roster.get('players')
        or []
    )

    opponent_player_ids = (
        opponent_roster.get('players')
        or []
    )

    my_players = build_players(
        my_player_ids,
        my_matchup.get('starters')
        or [],
        players,
        projections,
        actual,
        scoring,
        lookup,
    )

    opponent_players = build_players(
        opponent_player_ids,
        opponent_matchup.get('starters')
        or [],
        players,
        projections,
        actual,
        scoring,
        lookup,
    )

    def teamdata(
        roster,
        matchup,
        player_list,
    ):
        return {
            'id': roster['roster_id'],
            'name': tname(
                roster,
                users,
            ),
            'abbrev': tname(
                roster,
                users,
            ),
            'league': 'Sleeper',
            'players': player_list,
            'total': num(
                matchup.get('points')
            ),
            'actual_total': sum(
                num(
                    player.get('actual')
                )
                for player in player_list
                if player.get('starter')
            ),
            'projected_total': sum(
                num(
                    player.get('actual')
                    if player.get('actual')
                    is not None
                    else player.get(
                        'projected'
                    )
                )
                for player in player_list
                if player.get('starter')
            ),
        }

    my_team = teamdata(
        my_roster,
        my_matchup,
        my_players,
    )

    opponent_team = teamdata(
        opponent_roster,
        opponent_matchup,
        opponent_players,
    )

    return {
        'platform': 'Sleeper',
        'week': week,
        'league_name': (
            league_data.get('name')
            or league.get('name')
        ),
        'my_team': my_team,
        'opponent': opponent_team,
        'difference': (
            my_team['actual_total']
            - opponent_team['actual_total']
        ),
    }