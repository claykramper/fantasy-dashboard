import re
import unicodedata
import requests
from config import ESPN_COOKIES, ESPN_FANTASY_URL, ESPN_PARAMS, MY_OWNER_GUID, ESPN_SEASON
from nfl import build_game_lookup

SLOT_NAMES = {0:'QB',2:'RB',4:'WR',6:'TE',16:'D/ST',17:'K',23:'FLEX'}
LINEUP_ORDER = ['QB','RB','WR','TE','FLEX','K','D/ST']
SLOT_ORDER = {name:i for i,name in enumerate(LINEUP_ORDER)}

def normalize_name(value):
    text=unicodedata.normalize('NFKD',str(value or ''))
    text=''.join(c for c in text if not unicodedata.combining(c))
    text=text.lower().replace('’',"'")
    text=re.sub(r"[^a-z0-9 ]",'',text)
    suffixes={'jr','sr','ii','iii','iv','v'}
    return ' '.join(x for x in text.split() if x not in suffixes)

def get_league_data():
    response=requests.get(ESPN_FANTASY_URL,params=ESPN_PARAMS,cookies=ESPN_COOKIES,timeout=20)
    response.raise_for_status()
    return response.json()

def find_my_team(data):
    for team in data.get('teams',[]):
        if MY_OWNER_GUID in team.get('owners',[]): return team
    raise RuntimeError('Could not find your ESPN team.')

def find_matchup(data,my_team):
    scoring_period=data['scoringPeriodId']
    for game in data.get('schedule',[]):
        if game.get('matchupPeriodId') != scoring_period: continue
        home=game.get('home',{}); away=game.get('away',{})
        opponent_id=(away.get('teamId') if home.get('teamId')==my_team['id'] else home.get('teamId') if away.get('teamId')==my_team['id'] else None)
        if opponent_id is not None:
            return next(team for team in data['teams'] if team['id']==opponent_id)
    raise RuntimeError('Could not find current matchup.')

def get_players(team):
    out=[]
    for entry_index,entry in enumerate(team.get('roster',{}).get('entries',[])):
        slot_id=entry.get('lineupSlotId')
        player=entry.get('playerPoolEntry',{}).get('player',{})
        is_starter=slot_id in SLOT_NAMES
        out.append({
            'player_id':entry.get('playerId'),'name':player.get('fullName'),
            'slot':SLOT_NAMES.get(slot_id,'BENCH'),'lineup_slot_id':slot_id,
            'starter':is_starter,'bench':not is_starter,
            'injury_status':player.get('injuryStatus'),
            'pro_team_id':str(player.get('proTeamId')) if player.get('proTeamId') is not None else None,
            '_entry_index':entry_index,
        })
    # ESPN's API roster-entry order is not guaranteed to match the lineup UI.
    # Sort ONLY ESPN by the actual lineupSlotId, with FLEX before K/DST.
    return sorted(out,key=lambda p:(SLOT_ORDER.get(p['slot'],99) if p['starter'] else 99,p['_entry_index']))

def find_player_objects(data,player_id):
    out=[]
    def walk(value):
        if isinstance(value,dict):
            if value.get('id')==player_id: out.append(value)
            for child in value.values(): walk(child)
        elif isinstance(value,list):
            for child in value: walk(child)
    walk(data); return out

def get_player_stats(data,player_id):
    period=data['scoringPeriodId']; projected=[]; actual=[]; projected_stats={}
    for player in find_player_objects(data,player_id):
        for stat in player.get('stats',[]):
            if not isinstance(stat,dict) or stat.get('seasonId')!=int(ESPN_SEASON) or stat.get('scoringPeriodId')!=period: continue
            if stat.get('statSourceId')==1 and stat.get('statSplitTypeId')==1 and stat.get('appliedTotal') is not None:
                projected.append(float(stat['appliedTotal']))
                if not projected_stats: projected_stats=stat.get('stats',{}) or {}
            if stat.get('statSourceId')==0 and stat.get('statSplitTypeId')==1 and stat.get('appliedTotal') is not None:
                actual.append(float(stat['appliedTotal']))
    return (projected[0] if projected else None,actual[0] if actual else None,projected_stats)

def get_espn_projection_lookup(names):
    wanted={normalize_name(name) for name in names if name}
    if not wanted:return {}
    data=get_league_data(); period=data.get('scoringPeriodId'); result={}; seen=set()
    def walk(value):
        if isinstance(value,dict):
            player_obj=value.get('player') if isinstance(value.get('player'),dict) else value
            full_name=player_obj.get('fullName') if isinstance(player_obj,dict) else None
            if full_name:
                key=normalize_name(full_name)
                if key in wanted and key not in seen:
                    for stat in player_obj.get('stats',[]) or []:
                        if isinstance(stat,dict) and stat.get('seasonId')==int(ESPN_SEASON) and stat.get('scoringPeriodId')==period and stat.get('statSourceId')==1 and stat.get('statSplitTypeId')==1:
                            result[key]={'stats':stat.get('stats',{}) or {},'pro_team_id':player_obj.get('proTeamId'),'position_id':player_obj.get('defaultPositionId')}; seen.add(key); break
            for child in value.values(): walk(child)
        elif isinstance(value,list):
            for child in value: walk(child)
    walk(data); return result

def build_espn_matchup(nfl_games):
    data=get_league_data(); my_team=find_my_team(data); opponent=find_matchup(data,my_team); lookup=build_game_lookup(nfl_games)
    def build_team(team):
        players=[]; actual_total=0.0; projected_total=0.0
        for player in get_players(team):
            projected,actual,_=get_player_stats(data,player['player_id']); game=lookup.get(str(player.get('pro_team_id')), {})
            if player['starter'] and actual is not None: actual_total += actual
            if player['starter']: projected_total += actual if actual is not None else (projected or 0)
            players.append({'name':player['name'],'slot':player['slot'],'points':actual if actual is not None else projected,'projected':projected,'actual':actual,'status':'LOCKED' if 'FINAL' in str(game.get('game_status','')).upper() else 'PROJECTED','injury':player['injury_status'] or '','pro_team_id':player['pro_team_id'],'nfl_team':game.get('team',''),'opponent':game.get('opponent',''),'game_time':game.get('game_time',''),'game_status':game.get('game_status',''),'status_detail':game.get('status_detail',''),'starter':player['starter'],'bench':player['bench']})
        return {'id':team['id'],'name':team['name'],'abbrev':team['abbrev'],'league':'ESPN','players':players,'total':actual_total,'actual_total':actual_total,'projected_total':projected_total}
    my=build_team(my_team); opp=build_team(opponent)
    return {'platform':'ESPN','week':data['scoringPeriodId'],'my_team':my,'opponent':opp,'difference':my['actual_total']-opp['actual_total']}
