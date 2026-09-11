from nfl import (
    build_game_lookup,
    build_slate_data,
    get_next_slate_index,
    get_nfl_schedule,
)
from espn import build_espn_matchup
from sleeper import build_sleeper_matchup
from yahoo import get_yahoo_access_token
from yahoo_manual import build_manual_yahoo


def build_dashboard():
    nfl_games = get_nfl_schedule()
    slates = build_slate_data(nfl_games)
    game_lookup = build_game_lookup(nfl_games)

    sleeper = None
    sleeper_error = None
    try:
        sleeper = build_sleeper_matchup(game_lookup)
    except Exception as error:
        sleeper_error = str(error)

    espn = None
    espn_error = None
    try:
        espn = build_espn_matchup(nfl_games)
    except Exception as error:
        espn_error = str(error)

    manual_yahoo = None
    manual_yahoo_error = None
    try:
        manual_yahoo = build_manual_yahoo(game_lookup)
    except Exception as error:
        manual_yahoo_error = str(error)

    yahoo_connected = bool(get_yahoo_access_token())

    return {
        "slates": slates,
        "next_slate_id": get_next_slate_index(slates),
        "sleeper": sleeper,
        "sleeper_error": sleeper_error,
        "espn": espn,
        "espn_error": espn_error,
        "manual_yahoo": manual_yahoo,
        "manual_yahoo_error": manual_yahoo_error,
        "yahoo": {
            "connected": yahoo_connected,
            "status": (
                "Fantasy API access pending"
                if yahoo_connected
                else "Not connected"
            ),
        },
    }
