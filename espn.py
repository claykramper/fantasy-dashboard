import requests
from config import ESPN_COOKIES,ESPN_FANTASY_URL,ESPN_PARAMS,ESPN_SEASON,MY_OWNER_GUID
from nfl import build_game_lookup
SLOT_NAMES={0:'QB',2:'RB',4:'WR',6:'TE',16:'D/ST',17:'K',23:'FLEX'}; LINEUP_ORDER=['QB','RB','WR','TE','FLEX','K','D/ST']
def get_league_data():
 r=requests.get(ESPN_FANTASY_URL,params=ESPN_PARAMS,cookies=ESPN_COOKIES,timeout=20);r.raise_for_status();return r.json()
def find_my_team(data):
 for t in data.get('teams',[]):
  if MY_OWNER_GUID in t.get('owners',[]):return t
 raise RuntimeError('Could not find your ESPN team.')
def find_matchup(data,my):
 p=data['scoringPeriodId']
 for g in data.get('schedule',[]):
  if g.get('matchupPeriodId')!=p:continue
  h=g.get('home',{});a=g.get('away',{});oid=a.get('teamId') if h.get('teamId')==my['id'] else h.get('teamId') if a.get('teamId')==my['id'] else None
  if oid is not None:
   return next(t for t in data['teams'] if t['id']==oid)
 raise RuntimeError('Could not find current matchup.')
def get_players(team):
 out=[]
 for e in team.get('roster',{}).get('entries',[]):
  sid=e.get('lineupSlotId');p=e.get('playerPoolEntry',{}).get('player',{});out.append({'player_id':e.get('playerId'),'name':p.get('fullName'),'slot':SLOT_NAMES.get(sid,'BENCH'),'starter':sid in SLOT_NAMES,'injury_status':p.get('injuryStatus'),'pro_team_id':str(p.get('proTeamId')) if p.get('proTeamId') is not None else None})
 return out
def get_starters(ps):
 d={}
 for p in ps:
  if p['starter']:d.setdefault(p['slot'],[]).append(p)
 return [p for s in LINEUP_ORDER for p in d.get(s,[])]
def find_player_objects(data,pid):
 out=[]
 def w(o):
  if isinstance(o,dict):
   if o.get('id')==pid:out.append(o)
   for v in o.values():w(v)
  elif isinstance(o,list):
   for v in o:w(v)
 w(data);return out
def get_player_stats(data,pid):
 period=data['scoringPeriodId'];pr=[];ac=[]
 for p in find_player_objects(data,pid):
  for r in p.get('stats',[]):
   if not isinstance(r,dict) or r.get('seasonId')!=int(ESPN_SEASON) or r.get('scoringPeriodId')!=period:continue
   if r.get('statSourceId')==1 and r.get('statSplitTypeId')==1 and r.get('appliedTotal') is not None:pr.append(float(r['appliedTotal']))
   if r.get('statSourceId')==0 and r.get('statSplitTypeId')==1 and r.get('appliedTotal') is not None:ac.append(float(r['appliedTotal']))
 return (pr[0] if pr else None,ac[0] if ac else None)
def build_espn_matchup(nfl_games):
 data=get_league_data();my=find_my_team(data);opp=find_matchup(data,my);lookup=build_game_lookup(nfl_games)
 def team(t):
  ps=[];at=pt=0.0
  for p in get_starters(get_players(t)):
   proj,actual=get_player_stats(data,p['player_id']);x=lookup.get(str(p.get('pro_team_id')),{})
   if actual is not None:at+=actual;pt+=actual
   elif proj is not None:pt+=proj
   ps.append({'name':p['name'],'slot':p['slot'],'points':actual if actual is not None else proj,'projected':proj,'actual':actual,'status':'LOCKED' if actual is not None else 'PROJECTED','injury':p['injury_status'] or '','pro_team_id':p['pro_team_id'],'nfl_team':x.get('team',''),'opponent':x.get('opponent',''),'game_time':x.get('game_time',''),'game_status':x.get('game_status',''),'status_detail':x.get('status_detail','')})
  return {'id':t['id'],'name':t['name'],'abbrev':t['abbrev'],'league':'ESPN','players':ps,'total':at,'actual_total':at,'projected_total':pt}
 a=team(my);b=team(opp);return {'platform':'ESPN','week':data['scoringPeriodId'],'my_team':a,'opponent':b,'difference':a['actual_total']-b['actual_total']}
