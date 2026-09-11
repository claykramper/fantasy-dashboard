import requests,time
from config import SLEEPER_API_URL,SLEEPER_PROJECTIONS_URL,SLEEPER_STATS_URL,SLEEPER_USERNAME
PLAYER_CACHE=None;PLAYER_CACHE_TIME=0;PROJECTION_CACHE={};STATS_CACHE={}
def get(path):
 r=requests.get(f'{SLEEPER_API_URL}{path}',timeout=20);r.raise_for_status();return r.json()
def get_sleeper_user():return get(f'/user/{SLEEPER_USERNAME}')
def get_sleeper_leagues(uid):return get(f'/user/{uid}/leagues/nfl/2026')
def get_sleeper_state():return get('/state/nfl')
def get_sleeper_league(lid):return get(f'/league/{lid}')
def get_sleeper_rosters(lid):return get(f'/league/{lid}/rosters')
def get_sleeper_users(lid):return get(f'/league/{lid}/users')
def get_sleeper_matchups(lid,week):return get(f'/league/{lid}/matchups/{week}')
def get_sleeper_players():
 global PLAYER_CACHE,PLAYER_CACHE_TIME
 if PLAYER_CACHE is not None and time.time()-PLAYER_CACHE_TIME<86400:return PLAYER_CACHE
 PLAYER_CACHE=get('/players/nfl');PLAYER_CACHE_TIME=time.time();return PLAYER_CACHE
def choose_league(ls):
 if not ls:raise RuntimeError('No Sleeper NFL leagues found.')
 return next((x for x in ls if x.get('status')=='in_season'),ls[0])
def num(v):
 try:return float(v or 0)
 except:return 0.0
def rows(d):
 if isinstance(d,dict):return d
 return {str(x['player_id']):x for x in d if isinstance(x,dict) and x.get('player_id') is not None} if isinstance(d,list) else {}
def position(p):
 q=p.get('fantasy_positions') or [];return q[0] if q else p.get('position','')
def points(stats,scoring,pos):
 if not isinstance(stats,dict):return None
 total=0.0
 for k,v in scoring.items():
  if k in stats: total+=num(stats[k])*num(v)
 bonus={'RB':'bonus_rec_rb','WR':'bonus_rec_wr','TE':'bonus_rec_te'}.get(str(pos).upper())
 if bonus and bonus in scoring: total+=num(stats.get('rec'))*num(scoring[bonus])
 return round(total,2)
def score(pid,p,proj,actual,scoring):
 pr=rows(proj).get(str(pid)); ac=rows(actual).get(str(pid)); pos=position(p); projected=points(pr,scoring,pos) if pr else None; real=points(ac,scoring,pos) if ac and num(ac.get('gp'))>0 else None
 return projected,real
def game_info(team,lookup):
 g=lookup.get(str(team or '').upper()); return {'team':team or '','opponent':'','game_time':'','game_status':''} if not g else {'team':g['team'],'opponent':g['opponent'],'game_time':g['game_time'],'game_status':g['game_status']}
def build_players(matchup,players,proj,actual,scoring,lookup):
 out=[]
 for pid in matchup.get('starters',[]):
  p=players.get(str(pid));
  if not p:continue
  projected,real=score(pid,p,proj,actual,scoring); team=p.get('team') or ''; g=game_info(team,lookup); finished='FINAL' in str(g['game_status']).upper()
  name=p.get('full_name') or ' '.join(x for x in [p.get('first_name',''),p.get('last_name','')] if x)
  out.append({'name':name,'slot':position(p) or 'FLEX','player_id':str(pid),'nfl_team':g['team'],'opponent':g['opponent'],'game_time':g['game_time'],'game_status':g['game_status'],'points':real if real is not None else projected,'projected':projected,'actual':real,'injury':p.get('injury_status') or '','status':'LOCKED' if finished else ('LIVE' if real is not None else 'PROJECTED'),'pro_team_id':team})
 return out
def tname(roster,users):
 m=roster.get('metadata') or {}
 if m.get('team_name'):return m['team_name']
 for u in users:
  if u.get('user_id')==roster.get('owner_id'):return u.get('display_name') or u.get('username') or f"Roster {roster.get('roster_id')}"
 return f"Roster {roster.get('roster_id')}"
def build_sleeper_matchup(lookup):
 user=get_sleeper_user(); league=choose_league(get_sleeper_leagues(user['user_id'])); lid=league['league_id']; ld=get_sleeper_league(lid); week=int(get_sleeper_state().get('week') or 1); rosters=get_sleeper_rosters(lid); users=get_sleeper_users(lid); matchups=get_sleeper_matchups(lid,week); myr=next(r for r in rosters if r.get('owner_id')==user['user_id']); mym=next(m for m in matchups if m.get('roster_id')==myr['roster_id']); oppm=next(m for m in matchups if m.get('matchup_id')==mym.get('matchup_id') and m.get('roster_id')!=myr['roster_id']); oppr=next(r for r in rosters if r.get('roster_id')==oppm['roster_id']); players=get_sleeper_players(); pk=(2026,week)
 if pk not in PROJECTION_CACHE:
  r=requests.get(f'{SLEEPER_PROJECTIONS_URL}/2026/{week}',params={'season_type':'regular'},timeout=30);r.raise_for_status();PROJECTION_CACHE[pk]=(time.time(),r.json())
 if pk not in STATS_CACHE:
  r=requests.get(f'{SLEEPER_STATS_URL}/regular/2026/{week}',timeout=30);r.raise_for_status();STATS_CACHE[pk]=(time.time(),r.json())
 proj=PROJECTION_CACHE[pk][1]; actual=STATS_CACHE[pk][1]; scoring=ld.get('scoring_settings') or {}; mp=build_players(mym,players,proj,actual,scoring,lookup); op=build_players(oppm,players,proj,actual,scoring,lookup)
 def teamdata(r,m,ps):
  return {'id':r['roster_id'],'name':tname(r,users),'abbrev':tname(r,users),'league':'Sleeper','players':ps,'total':num(m.get('points')),'actual_total':sum(num(x.get('actual')) for x in ps),'projected_total':sum(num(x.get('actual') if x.get('actual') is not None else x.get('projected')) for x in ps)}
 mt=teamdata(myr,mym,mp);ot=teamdata(oppr,oppm,op);return {'platform':'Sleeper','week':week,'league_name':ld.get('name') or league.get('name'),'my_team':mt,'opponent':ot,'difference':mt['total']-ot['total']}
