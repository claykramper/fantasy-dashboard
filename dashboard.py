from espn import build_espn_matchup
from nfl import build_game_lookup,build_slate_data,get_next_slate_index,get_nfl_schedule
from sleeper import build_sleeper_matchup
from yahoo import get_yahoo_access_token

def build_dashboard():
    nfl_games=get_nfl_schedule(); slates=build_slate_data(nfl_games); lookup=build_game_lookup(nfl_games)
    sleeper=None; sleeper_error=None
    try:sleeper=build_sleeper_matchup(lookup)
    except Exception as e:sleeper_error=str(e)
    espn=None; espn_error=None
    try:espn=build_espn_matchup(nfl_games)
    except Exception as e:espn_error=str(e)
    return {'slates':slates,'next_slate_id':get_next_slate_index(slates),'sleeper':sleeper,'sleeper_error':sleeper_error,'yahoo':{'connected':bool(get_yahoo_access_token()),'status':'Fantasy API access pending' if get_yahoo_access_token() else 'Not connected'},'espn':espn,'espn_error':espn_error}
