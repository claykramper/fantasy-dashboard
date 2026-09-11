import os, secrets
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv()
LOCAL_TIMEZONE=ZoneInfo('America/Chicago')
SECRET_KEY=os.getenv('FLASK_SECRET_KEY',secrets.token_hex(32))
ESPN_SWID=os.getenv('ESPN_SWID'); ESPN_S2=os.getenv('ESPN_S2'); ESPN_LEAGUE_ID=os.getenv('ESPN_LEAGUE_ID'); ESPN_SEASON=os.getenv('ESPN_SEASON','2026')
MY_OWNER_GUID=os.getenv('ESPN_OWNER_GUID','{DE1DCE7E-4046-4158-A37D-10DD7C1923A0}')
ESPN_FANTASY_URL=f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{ESPN_SEASON}/segments/0/leagues/{ESPN_LEAGUE_ID}'
ESPN_SCOREBOARD_URL='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'
ESPN_COOKIES={'SWID':ESPN_SWID,'espn_s2':ESPN_S2}
ESPN_PARAMS=[('view','mTeam'),('view','mRoster'),('view','mMatchup'),('view','kona_player_info')]
YAHOO_CLIENT_ID=os.getenv('YAHOO_CLIENT_ID'); YAHOO_CLIENT_SECRET=os.getenv('YAHOO_CLIENT_SECRET'); YAHOO_REDIRECT_URI=os.getenv('YAHOO_REDIRECT_URI')
YAHOO_FANTASY_URL='https://fantasysports.yahooapis.com/fantasy/v2'; YAHOO_AUTH_URL='https://api.login.yahoo.com/oauth2/request_auth'; YAHOO_TOKEN_URL='https://api.login.yahoo.com/oauth2/get_token'
SLEEPER_USERNAME=os.getenv('SLEEPER_USERNAME','kramps247'); SLEEPER_API_URL='https://api.sleeper.app/v1'; SLEEPER_PROJECTIONS_URL='https://api.sleeper.com/projections/nfl'; SLEEPER_STATS_URL='https://api.sleeper.app/v1/stats/nfl'
