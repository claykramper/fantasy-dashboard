import time
from datetime import datetime,timedelta
import requests
from config import ESPN_SCOREBOARD_URL,LOCAL_TIMEZONE

def get_nfl_schedule():
    games=[]; today=datetime.now(LOCAL_TIMEZONE).date()
    for offset in range(8):
        day=today+timedelta(days=offset)
        try:
            r=requests.get(ESPN_SCOREBOARD_URL,params={'dates':day.strftime('%Y%m%d')},timeout=20); r.raise_for_status(); data=r.json()
        except Exception: continue
        for event in data.get('events',[]):
            comps=event.get('competitions',[])
            if not comps: continue
            comp=comps[0]; competitors=comp.get('competitors',[])
            if len(competitors)<2: continue
            home=next((c for c in competitors if c.get('homeAway')=='home'),competitors[0]); away=next((c for c in competitors if c.get('homeAway')=='away'),competitors[1])
            kickoff_text=event.get('date') or comp.get('date')
            if not kickoff_text: continue
            try: kickoff=datetime.fromisoformat(kickoff_text.replace('Z','+00:00'))
            except ValueError: continue
            st=comp.get('status',{}).get('type',{})
            games.append({'id':str(event.get('id')),'kickoff':kickoff,'home':{'id':str(home.get('id','')),'abbreviation':home.get('team',{}).get('abbreviation','')},'away':{'id':str(away.get('id','')),'abbreviation':away.get('team',{}).get('abbreviation','')},'status':st.get('name',''),'status_detail':st.get('detail',st.get('shortDetail',''))})
    games.sort(key=lambda g:g['kickoff']); return games

def group_games_into_slates(games):
    if not games:return []
    slates=[]; current=None
    for game in sorted(games,key=lambda g:g['kickoff']):
        if current is None or (game['kickoff']-current['kickoff']).total_seconds()>2700:
            current={'kickoff':game['kickoff'],'games':[game]}; slates.append(current)
        else: current['games'].append(game)
    return slates

def format_slate_label(kickoff): return kickoff.astimezone(LOCAL_TIMEZONE).strftime('%a %I:%M %p').lstrip('0')
def format_game_time(kickoff): return kickoff.astimezone(LOCAL_TIMEZONE).strftime('%I:%M %p').lstrip('0')

def build_slate_data(games):
    now=datetime.now(LOCAL_TIMEZONE); out=[]
    for i,slate in enumerate(group_games_into_slates(games)):
        kickoff=slate['kickoff'].astimezone(LOCAL_TIMEZONE)
        out.append({'id':i,'label':format_slate_label(slate['kickoff']),'date':kickoff.strftime('%Y-%m-%d'),'kickoff':kickoff.isoformat(),'timestamp':slate['kickoff'].timestamp(),'is_upcoming':slate['kickoff']>now,'games':[{'id':g['id'],'away':g['away']['abbreviation'],'home':g['home']['abbreviation'],'away_id':g['away']['id'],'home_id':g['home']['id'],'kickoff':g['kickoff'].isoformat(),'game_time':format_game_time(g['kickoff']),'game_status':g['status'],'status_detail':g['status_detail']} for g in slate['games']]})
    return out

def get_next_slate_index(slates):
    now=time.time()
    for s in slates:
        if s['timestamp']>now:return s['id']
    return None

def build_game_lookup(games):
    lookup={}
    for g in games:
        home_id=str(g['home']['id']); away_id=str(g['away']['id']); k=g['kickoff'].astimezone(LOCAL_TIMEZONE)
        h={'team':g['home']['abbreviation'],'opponent':g['away']['abbreviation'],'opponent_id':away_id,'home':True,'kickoff':k,'game_time':format_game_time(g['kickoff']),'game_status':g['status'],'status_detail':g['status_detail']}
        a={'team':g['away']['abbreviation'],'opponent':g['home']['abbreviation'],'opponent_id':home_id,'home':False,'kickoff':k,'game_time':format_game_time(g['kickoff']),'game_status':g['status'],'status_detail':g['status_detail']}
        lookup[home_id]=h; lookup[away_id]=a; lookup[g['home']['abbreviation'].upper()]=h; lookup[g['away']['abbreviation'].upper()]=a
    return lookup
