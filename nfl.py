from datetime import datetime, timedelta

import requests

from config import ESPN_SCOREBOARD_URL, LOCAL_TIMEZONE


def get_nfl_schedule():
    """
    Return all NFL games belonging to the current dashboard/fantasy week.

    The dashboard week runs Tuesday through Monday.

    This intentionally uses a Tuesday-to-Monday window rather than assuming
    NFL games only occur Thursday through Monday. That allows the dashboard
    to automatically handle:
      - Wednesday games
      - Thursday/Thanksgiving games
      - Friday/Black Friday games
      - Saturday games
      - Sunday games
      - multiple Monday games
      - other unusual/special NFL scheduling

    On Tuesday, the previous Monday is considered complete and the dashboard
    rolls forward to the new Tuesday-to-Monday window.
    """

    now = datetime.now(LOCAL_TIMEZONE)
    today = now.date()

    # Python weekday:
    # Monday    = 0
    # Tuesday   = 1
    # Wednesday = 2
    # Thursday  = 3
    # Friday    = 4
    # Saturday  = 5
    # Sunday    = 6

    weekday = today.weekday()

    # Tuesday is the beginning of our dashboard/fantasy-week window.
    #
    # On:
    #   Tuesday    -> today
    #   Wednesday  -> yesterday
    #   Thursday   -> 2 days ago
    #   ...
    #   Monday     -> 6 days ago
    #
    # Therefore every day from Tuesday through Monday belongs to the same
    # dashboard week.
    days_since_tuesday = (weekday - 1) % 7
    week_start = today - timedelta(days=days_since_tuesday)

    # Tuesday through Monday is seven calendar days.
    week_end = week_start + timedelta(days=6)

    games = []

    for offset in range(7):
        day = week_start + timedelta(days=offset)

        try:
            response = requests.get(
                ESPN_SCOREBOARD_URL,
                params={'dates': day.strftime('%Y%m%d')},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            continue

        for event in data.get('events', []):
            competitions = event.get('competitions', [])

            if not competitions:
                continue

            competition = competitions[0]
            competitors = competition.get('competitors', [])

            if len(competitors) < 2:
                continue

            home = next(
                (
                    competitor
                    for competitor in competitors
                    if competitor.get('homeAway') == 'home'
                ),
                competitors[0],
            )

            away = next(
                (
                    competitor
                    for competitor in competitors
                    if competitor.get('homeAway') == 'away'
                ),
                competitors[1],
            )

            kickoff_text = (
                event.get('date')
                or competition.get('date')
            )

            if not kickoff_text:
                continue

            try:
                kickoff = datetime.fromisoformat(
                    kickoff_text.replace('Z', '+00:00')
                )
            except ValueError:
                continue

            status = competition.get('status', {}).get('type', {})

            games.append({
                'id': str(event.get('id')),
                'kickoff': kickoff,
                'home': {
                    'id': str(home.get('id', '')),
                    'abbreviation': (
                        home.get('team', {}).get('abbreviation', '')
                    ),
                },
                'away': {
                    'id': str(away.get('id', '')),
                    'abbreviation': (
                        away.get('team', {}).get('abbreviation', '')
                    ),
                },
                'status': status.get('name', ''),
                'status_detail': status.get(
                    'detail',
                    status.get('shortDetail', ''),
                ),
            })

    # ESPN can theoretically return duplicate events when querying dates
    # individually, so deduplicate by event ID.
    unique = {}

    for game in games:
        unique[game['id']] = game

    games = list(unique.values())
    games.sort(key=lambda game: game['kickoff'])

    return games


def group_games_into_slates(games):
    if not games:
        return []

    slates = []
    current = None

    for game in sorted(games, key=lambda game: game['kickoff']):
        if (
            current is None
            or (
                game['kickoff'] - current['kickoff']
            ).total_seconds() > 2700
        ):
            current = {
                'kickoff': game['kickoff'],
                'games': [game],
            }
            slates.append(current)
        else:
            current['games'].append(game)

    return slates


def format_slate_label(kickoff):
    return (
        kickoff
        .astimezone(LOCAL_TIMEZONE)
        .strftime('%a %I:%M %p')
        .lstrip('0')
    )


def format_game_time(kickoff):
    return (
        kickoff
        .astimezone(LOCAL_TIMEZONE)
        .strftime('%I:%M %p')
        .lstrip('0')
    )


def build_slate_data(games):
    now = datetime.now(LOCAL_TIMEZONE)
    out = []

    for index, slate in enumerate(
        group_games_into_slates(games)
    ):
        kickoff = slate['kickoff'].astimezone(LOCAL_TIMEZONE)

        out.append({
            'id': index,
            'label': format_slate_label(slate['kickoff']),
            'date': kickoff.strftime('%Y-%m-%d'),
            'kickoff': kickoff.isoformat(),
            'timestamp': slate['kickoff'].timestamp(),
            'is_upcoming': slate['kickoff'] > now,
            'games': [
                {
                    'id': game['id'],
                    'away': game['away']['abbreviation'],
                    'home': game['home']['abbreviation'],
                    'away_id': game['away']['id'],
                    'home_id': game['home']['id'],
                    'kickoff': game['kickoff'].isoformat(),
                    'game_time': format_game_time(
                        game['kickoff']
                    ),
                    'game_status': game['status'],
                    'status_detail': game['status_detail'],
                }
                for game in slate['games']
            ],
        })

    return out


def get_next_slate_index(slates):
    now = datetime.now(LOCAL_TIMEZONE).timestamp()

    for slate in slates:
        if slate['timestamp'] > now:
            return slate['id']

    return None


def build_game_lookup(games):
    lookup = {}

    for game in games:
        home_id = str(game['home']['id'])
        away_id = str(game['away']['id'])

        kickoff = game['kickoff'].astimezone(LOCAL_TIMEZONE)

        home_info = {
            'team': game['home']['abbreviation'],
            'opponent': game['away']['abbreviation'],
            'opponent_id': away_id,
            'team_id': home_id,
            'home': True,
            'kickoff': kickoff,
            'game_time': format_game_time(kickoff),
            'game_status': game['status'],
            'status_detail': game['status_detail'],
        }

        away_info = {
            'team': game['away']['abbreviation'],
            'opponent': game['home']['abbreviation'],
            'opponent_id': home_id,
            'team_id': away_id,
            'home': False,
            'kickoff': kickoff,
            'game_time': format_game_time(kickoff),
            'game_status': game['status'],
            'status_detail': game['status_detail'],
        }

        lookup[home_id] = home_info
        lookup[away_id] = away_info

        home_abbreviation = (
            game['home']['abbreviation'] or ''
        ).upper()

        away_abbreviation = (
            game['away']['abbreviation'] or ''
        ).upper()

        if home_abbreviation:
            lookup[home_abbreviation] = home_info

        if away_abbreviation:
            lookup[away_abbreviation] = away_info

    return lookup