import base64,secrets,requests
from urllib.parse import urlencode
from flask import redirect,request,session
from config import YAHOO_AUTH_URL,YAHOO_CLIENT_ID,YAHOO_CLIENT_SECRET,YAHOO_FANTASY_URL,YAHOO_REDIRECT_URI,YAHOO_TOKEN_URL

def yahoo_login():
    state=secrets.token_urlsafe(32); session['yahoo_oauth_state']=state
    p={'client_id':YAHOO_CLIENT_ID,'redirect_uri':YAHOO_REDIRECT_URI,'response_type':'code','state':state}
    return redirect(f'{YAHOO_AUTH_URL}?{urlencode(p)}')
def yahoo_callback():
    if request.args.get('state')!=session.get('yahoo_oauth_state'): return 'Invalid Yahoo OAuth state.',400
    code=request.args.get('code')
    if not code:return 'Yahoo did not return an authorization code.',400
    creds=base64.b64encode(f'{YAHOO_CLIENT_ID}:{YAHOO_CLIENT_SECRET}'.encode()).decode()
    r=requests.post(YAHOO_TOKEN_URL,headers={'Authorization':f'Basic {creds}','Content-Type':'application/x-www-form-urlencoded'},data={'grant_type':'authorization_code','redirect_uri':YAHOO_REDIRECT_URI,'code':code},timeout=20); r.raise_for_status(); d=r.json()
    session['yahoo_access_token']=d.get('access_token'); session['yahoo_refresh_token']=d.get('refresh_token'); session.pop('yahoo_oauth_state',None); return redirect('/yahoo')
def get_yahoo_access_token(): return session.get('yahoo_access_token')
def yahoo_api_request(token,path):
    r=requests.get(f'{YAHOO_FANTASY_URL}/{path}',headers={'Authorization':f'Bearer {token}'},params={'format':'json'},timeout=20); r.raise_for_status(); return r.json()
def get_yahoo_games(token): return yahoo_api_request(token,'users;use_login=1/games;game_codes=nfl')
def get_yahoo_leagues(token): return yahoo_api_request(token,'users;use_login=1/games;game_codes=nfl/leagues')
