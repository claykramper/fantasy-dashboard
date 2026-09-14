from espn import build_espn_matchup
from nfl import build_game_lookup, build_slate_data, get_next_slate_index, get_nfl_schedule
from sleeper import build_sleeper_matchup
from yahoo_sync_store import get_latest_yahoo


def yahoo_player(player):
    return {
        'name': player.get('name'),
        'slot': player.get('slot') or player.get('position') or '',
        'actual': player.get('points'),
        'projected': player.get('projected_points'),
        'injury': player.get('injury_status'),
        'game_status': player.get('game_status'),
        'status': player.get('status'),
        'nfl_team': player.get('team'),
        'opponent': player.get('opponent'),
        'game_time': player.get('game_time'),
    }


def yahoo_team(abbrev, team_name, players):
    return {
        'abbrev': abbrev,
        'team_name': team_name,
        'actual_total': sum(float(p.get('points') or 0) for p in players),
        'projected_total': None,
        'players': [yahoo_player(p) for p in players],
    }


def build_yahoo_matchup(data):
    if not data:
        return None

    matchup = data.get('current_matchup') or {}
    roster = data.get('roster') or []
    opponent_roster = matchup.get('opponent_roster') or []

    return {
        'league_name': data.get('league_name'),
        'week': matchup.get('week'),
        'my_team': yahoo_team(data.get('team_name') or 'Yahoo', data.get('team_name') or 'Yahoo', roster),
        'opponent': yahoo_team(matchup.get('opponent') or 'Opponent', matchup.get('opponent') or 'Opponent', opponent_roster),
        'actual_total': matchup.get('my_score'),
        'opponent_actual_total': matchup.get('opp_score'),
        'my_score': matchup.get('my_score'),
        'opp_score': matchup.get('opp_score'),
        'game_status': matchup.get('game_status'),
    }


def build_dashboard():
    nfl_games = get_nfl_schedule()
    slates = build_slate_data(nfl_games)
    lookup = build_game_lookup(nfl_games)

    sleeper = None
    sleeper_error = None
    try:
        sleeper = build_sleeper_matchup(lookup)
    except Exception as e:
        sleeper_error = str(e)

    espn = None
    espn_error = None
    try:
        espn = build_espn_matchup(nfl_games)
    except Exception as e:
        espn_error = str(e)

    yahoo_data = get_latest_yahoo()
    yahoo = build_yahoo_matchup(yahoo_data)
    yahoo_error = None if yahoo else 'Yahoo data has not been synced yet.'

    return {
        'slates': slates,
        'next_slate_id': get_next_slate_index(slates),
        'sleeper': sleeper,
        'sleeper_error': sleeper_error,
        'espn': espn,
        'espn_error': espn_error,
        'yahoo': yahoo,
        'yahoo_error': yahoo_error,
    }
