
import os
import time
import secrets
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

import requests
from flask import (
    Flask,
    jsonify,
    render_template_string,
    redirect,
    request,
    session,
)
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIG
# ============================================================

# ESPN
ESPN_SWID = os.getenv("ESPN_SWID")
ESPN_S2 = os.getenv("ESPN_S2")
LEAGUE_ID = os.getenv("ESPN_LEAGUE_ID")
SEASON = os.getenv("ESPN_SEASON")

MY_OWNER_GUID = "{DE1DCE7E-4046-4158-A37D-10DD7C1923A0}"

ESPN_FANTASY_URL = (
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
    f"seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
)

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
)

ESPN_COOKIES = {
    "SWID": ESPN_SWID,
    "espn_s2": ESPN_S2,
}

ESPN_PARAMS = [
    ("view", "mTeam"),
    ("view", "mRoster"),
    ("view", "mMatchup"),
    ("view", "kona_player_info"),
]


# Yahoo
YAHOO_CLIENT_ID = os.getenv("YAHOO_CLIENT_ID")
YAHOO_CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET")
YAHOO_REDIRECT_URI = os.getenv("YAHOO_REDIRECT_URI")

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

YAHOO_FANTASY_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

# Used to protect the Yahoo OAuth state value.
# Put FLASK_SECRET_KEY in Render for a stable value.
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

LOCAL_TIMEZONE = ZoneInfo("America/Chicago")


# ============================================================
# ESPN FUNCTIONS
# ============================================================

def get_league_data():
    response = requests.get(
        ESPN_FANTASY_URL,
        params=ESPN_PARAMS,
        cookies=ESPN_COOKIES,
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def get_nfl_schedule():
    response = requests.get(
        ESPN_SCOREBOARD_URL,
        params={"limit": 100},
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def group_games_into_slates(events):
    games = []

    for event in events:
        competitions = event.get("competitions", [])

        if not competitions:
            continue

        competition = competitions[0]

        kickoff = competition.get("date")

        if not kickoff:
            continue

        try:
            kickoff_dt = datetime.fromisoformat(
                kickoff.replace("Z", "+00:00")
            )
        except ValueError:
            continue

        local_kickoff = kickoff_dt.astimezone(LOCAL_TIMEZONE)

        games.append(
            {
                "id": event.get("id"),
                "name": event.get("name", ""),
                "short_name": event.get("shortName", ""),
                "date": kickoff,
                "local_date": local_kickoff.strftime("%Y-%m-%d"),
                "local_time": local_kickoff,
                "home_team": competition.get("competitors", [{}])[0]
                .get("team", {})
                .get("abbreviation", ""),
                "away_team": competition.get("competitors", [{}])[1]
                .get("team", {})
                .get("abbreviation", "")
                if len(competition.get("competitors", [])) > 1
                else "",
            }
        )

    games.sort(key=lambda x: x["local_time"])

    slates = []

    for game in games:
        local_time = game["local_time"]

        found = None

        for slate in slates:
            if slate["date"] != game["local_date"]:
                continue

            difference = abs(
                (local_time - slate["first_kickoff"]).total_seconds()
            )

            # Games within 90 minutes are considered part of the same slate.
            if difference <= 90 * 60:
                found = slate
                break

        if found:
            found["games"].append(game)

            if local_time < found["first_kickoff"]:
                found["first_kickoff"] = local_time
        else:
            slates.append(
                {
                    "date": game["local_date"],
                    "first_kickoff": local_time,
                    "games": [game],
                }
            )

    return slates


def format_slate_label(slate):
    first_game = slate["first_kickoff"]

    date_label = first_game.strftime("%a %b %-d")

    try:
        time_label = first_game.strftime("%-I:%M %p")
    except ValueError:
        time_label = first_game.strftime("%I:%M %p").lstrip("0")

    return f"{date_label} — {time_label}"


def format_game_time(kickoff):
    local_kickoff = kickoff.astimezone(LOCAL_TIMEZONE)

    if os.name == "nt":
        return local_kickoff.strftime("%#I:%M %p")

    return local_kickoff.strftime("%-I:%M %p")


def build_slate_data():
    data = get_nfl_schedule()
    events = data.get("events", [])

    slates = group_games_into_slates(events)

    output = []

    for index, slate in enumerate(slates):
        games = []

        for game in slate["games"]:
            games.append(
                {
                    "id": game["id"],
                    "short_name": game["short_name"],
                    "home_team": game["home_team"],
                    "away_team": game["away_team"],
                    "game_time": format_game_time(game["local_time"]),
                }
            )

        output.append(
            {
                "index": index,
                "date": slate["date"],
                "label": format_slate_label(slate),
                "games": games,
            }
        )

    return output


def get_next_slate_index(slates):
    now = datetime.now(LOCAL_TIMEZONE)

    for slate in slates:
        if slate["games"]:
            first_game_time = slate["games"][0]["local_time"]

            if first_game_time > now:
                return slates.index(slate)

    return max(len(slates) - 1, 0)


def find_my_team(league_data):
    for team in league_data.get("teams", []):
        owners = team.get("owners", [])

        for owner in owners:
            if owner.get("id") == MY_OWNER_GUID:
                return team

    return None


def find_matchup(league_data, my_team):
    if not my_team:
        return None

    my_team_id = my_team.get("id")

    for matchup in league_data.get("schedule", []):
        teams = matchup.get("teams", [])

        team_ids = [
            team.get("teamId")
            for team in teams
        ]

        if my_team_id in team_ids:
            return matchup

    return None


def get_players(team):
    roster = team.get("roster", {})
    entries = roster.get("entries", [])

    return entries


def get_starters(team):
    starters = []

    for entry in get_players(team):
        lineup_slot = entry.get("lineupSlotId")

        # ESPN lineup slot IDs:
        # 0 QB
        # 2 RB
        # 4 WR
        # 6 TE
        # 16 D/ST
        # 17 K
        # 23 FLEX
        #
        # Bench = 20
        if lineup_slot != 20:
            starters.append(entry)

    return starters


def find_player_objects(league_data):
    players = {}

    for player in league_data.get("players", []):
        player_id = player.get("id")

        if player_id is not None:
            players[player_id] = player

    return players


def get_player_stats(player):
    stats = player.get("stats", [])

    if not stats:
        return {}

    latest = stats[-1]

    return latest


def get_player_score(player):
    stats = get_player_stats(player)

    return stats.get("appliedTotal", 0) or 0


def build_game_lookup(scoreboard):
    lookup = {}

    for event in scoreboard.get("events", []):
        event_id = event.get("id")

        competitions = event.get("competitions", [])

        if not competitions:
            continue

        competition = competitions[0]

        for competitor in competition.get("competitors", []):
            team = competitor.get("team", {})
            abbreviation = team.get("abbreviation")

            if abbreviation:
                lookup[abbreviation] = {
                    "event_id": event_id,
                    "status": competition.get("status", {}),
                    "date": event.get("date"),
                }

    return lookup


def get_player_game_info(player, game_lookup):
    pro_team = player.get("proTeamId")

    if not pro_team:
        return {
            "game_status": "",
            "game_time": "",
        }

    return {
        "game_status": "",
        "game_time": "",
    }


def build_team_data(team, player_objects, game_lookup):
    if not team:
        return None

    starters = get_starters(team)

    players = []

    for entry in starters:
        player_id = entry.get("playerId")

        player = player_objects.get(player_id, {})

        player_name = (
            player.get("fullName")
            or player.get("name")
            or f"Player {player_id}"
        )

        position = player.get("defaultPositionId")

        players.append(
            {
                "name": player_name,
                "position": position,
                "starter": True,
                "fantasy_points": get_player_score(player),
                "projection": 0,
                "injury": player.get("injuryStatus"),
                "nfl_team": "",
                "opponent": "",
                "game_time": "",
                "game_status": "",
            }
        )

    return {
        "team_id": team.get("id"),
        "team_name": team.get("name", "Unknown Team"),
        "abbreviation": team.get("abbrev", ""),
        "score": team.get("record", {}).get("overall", {}).get("wins", 0),
        "players": players,
    }


def build_dashboard():
    league_data = get_league_data()

    scoreboard = get_nfl_schedule()

    player_objects = find_player_objects(league_data)

    my_team = find_my_team(league_data)

    matchup = find_matchup(league_data, my_team)

    opponent = None

    if matchup:
        for team in matchup.get("teams", []):
            if team.get("teamId") != my_team.get("id"):
                for league_team in league_data.get("teams", []):
                    if league_team.get("id") == team.get("teamId"):
                        opponent = league_team
                        break

    slates = build_slate_data()

    my_team_data = build_team_data(
        my_team,
        player_objects,
        build_game_lookup(scoreboard),
    )

    opponent_data = build_team_data(
        opponent,
        player_objects,
        build_game_lookup(scoreboard),
    )

    return {
        "platform": "ESPN",
        "league_name": league_data.get("name", "ESPN League"),
        "my_team": my_team_data,
        "opponent": opponent_data,
        "slates": slates,
        "next_slate": get_next_slate_index(
            [
                {
                    "games": [
                        {
                            "local_time": datetime.now(LOCAL_TIMEZONE)
                        }
                    ]
                }
            ]
        )
        if not slates
        else 0,
    }


# ============================================================
# YAHOO FUNCTIONS
# ============================================================

def yahoo_api_request(access_token, path):
    url = f"{YAHOO_FANTASY_URL}/{path}"

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        params={
            "format": "json",
        },
        timeout=20,
    )

    return response


def get_yahoo_access_token():
    return session.get("yahoo_access_token")


def get_yahoo_games():
    access_token = get_yahoo_access_token()

    if not access_token:
        return None

    response = yahoo_api_request(
        access_token,
        "users;use_login=1/games;game_codes=nfl",
    )

    if response.status_code != 200:
        return {
            "error": True,
            "status_code": response.status_code,
            "message": response.text,
        }

    return response.json()


def get_yahoo_leagues():
    access_token = get_yahoo_access_token()

    if not access_token:
        return None

    response = yahoo_api_request(
        access_token,
        "users;use_login=1/games;game_codes=nfl/games/leagues",
    )

    if response.status_code != 200:
        return {
            "error": True,
            "status_code": response.status_code,
            "message": response.text,
        }

    return response.json()


# ============================================================
# YAHOO OAUTH ROUTES
# ============================================================

@app.route("/yahoo/login")
def yahoo_login():
    if not YAHOO_CLIENT_ID or not YAHOO_CLIENT_SECRET:
        return jsonify(
            {
                "error": "Yahoo OAuth environment variables are missing."
            }
        ), 500

    state = secrets.token_urlsafe(32)

    session["yahoo_oauth_state"] = state

    params = {
        "client_id": YAHOO_CLIENT_ID,
        "redirect_uri": YAHOO_REDIRECT_URI,
        "response_type": "code",
        "state": state,
    }

    authorization_url = (
        f"{YAHOO_AUTH_URL}?{urlencode(params)}"
    )

    return redirect(authorization_url)


@app.route("/yahoo/callback")
def yahoo_callback():
    error = request.args.get("error")

    if error:
        return jsonify(
            {
                "yahoo_authentication_successful": False,
                "error": error,
            }
        ), 400

    state = request.args.get("state")
    saved_state = session.get("yahoo_oauth_state")

    if not state or state != saved_state:
        return jsonify(
            {
                "yahoo_authentication_successful": False,
                "error": "Invalid OAuth state.",
            }
        ), 400

    code = request.args.get("code")

    if not code:
        return jsonify(
            {
                "yahoo_authentication_successful": False,
                "error": "No authorization code returned by Yahoo.",
            }
        ), 400

    response = requests.post(
        YAHOO_TOKEN_URL,
        auth=(
            YAHOO_CLIENT_ID,
            YAHOO_CLIENT_SECRET,
        ),
        data={
            "grant_type": "authorization_code",
            "redirect_uri": YAHOO_REDIRECT_URI,
            "code": code,
        },
        timeout=20,
    )

    if response.status_code != 200:
        return jsonify(
            {
                "yahoo_authentication_successful": False,
                "status_code": response.status_code,
                "response": response.text,
            }
        ), 400

    token_data = response.json()

    access_token = token_data.get("access_token")

    if not access_token:
        return jsonify(
            {
                "yahoo_authentication_successful": False,
                "error": "Yahoo did not return an access token.",
            }
        ), 400

    # Store the access token in the Flask session temporarily.
    session["yahoo_access_token"] = access_token

    # Keep the refresh token temporarily as well.
    # We will handle persistent token storage properly later.
    if token_data.get("refresh_token"):
        session["yahoo_refresh_token"] = token_data["refresh_token"]

    session.pop("yahoo_oauth_state", None)

    return redirect("/yahoo")


# ============================================================
# YAHOO TEST PAGE
# ============================================================

@app.route("/yahoo")
def yahoo_page():
    access_token = get_yahoo_access_token()

    if not access_token:
        return render_template_string(
            """
            <!doctype html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Yahoo Fantasy</title>
                <style>
                    body {
                        background: #111;
                        color: #eee;
                        font-family: Arial, sans-serif;
                        padding: 30px;
                    }

                    a {
                        color: #7db7ff;
                    }

                    .card {
                        background: #1d1d1d;
                        border-radius: 12px;
                        padding: 20px;
                        margin-bottom: 15px;
                    }
                </style>
            </head>

            <body>
                <div class="card">
                    <h1>Yahoo Fantasy</h1>
                    <p>You are not currently authenticated with Yahoo.</p>
                    <a href="/yahoo/login">Connect Yahoo</a>
                </div>
            </body>
            </html>
            """
        )

    games = get_yahoo_games()
    leagues = get_yahoo_leagues()

    return render_template_string(
        """
        <!doctype html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Yahoo Fantasy</title>

            <style>
                body {
                    background: #111;
                    color: #eee;
                    font-family: Arial, sans-serif;
                    padding: 20px;
                    max-width: 800px;
                    margin: auto;
                }

                h1 {
                    margin-bottom: 5px;
                }

                .subtitle {
                    color: #aaa;
                    margin-bottom: 20px;
                }

                .card {
                    background: #1d1d1d;
                    border-radius: 12px;
                    padding: 18px;
                    margin-bottom: 15px;
                }

                .success {
                    color: #65d98b;
                }

                .error {
                    color: #ff7777;
                }

                pre {
                    white-space: pre-wrap;
                    word-break: break-word;
                    background: #0b0b0b;
                    padding: 12px;
                    border-radius: 8px;
                    overflow-x: auto;
                }

                a {
                    color: #7db7ff;
                }
            </style>
        </head>

        <body>

            <h1>Yahoo Fantasy</h1>

            <div class="subtitle">
                Yahoo connection test
            </div>

            <div class="card">
                <h2 class="success">
                    ✓ Yahoo authentication successful
                </h2>

                <p>
                    Your app successfully received a Yahoo OAuth access token.
                </p>
            </div>

            <div class="card">
                <h2>NFL Fantasy Games</h2>

                {% if games and games.error %}
                    <p class="error">
                        Yahoo Fantasy API returned an error:
                    </p>
                    <pre>{{ games | tojson(indent=2) }}</pre>
                {% elif games %}
                    <p class="success">
                        ✓ Yahoo Fantasy API responded
                    </p>
                    <pre>{{ games | tojson(indent=2) }}</pre>
                {% else %}
                    <p>No game data returned.</p>
                {% endif %}
            </div>

            <div class="card">
                <h2>Your Yahoo Fantasy Leagues</h2>

                {% if leagues and leagues.error %}
                    <p class="error">
                        Yahoo Fantasy League API returned an error:
                    </p>
                    <pre>{{ leagues | tojson(indent=2) }}</pre>
                {% elif leagues %}
                    <p class="success">
                        ✓ League data returned
                    </p>
                    <pre>{{ leagues | tojson(indent=2) }}</pre>
                {% else %}
                    <p>No league data returned.</p>
                {% endif %}
            </div>

            <div class="card">
                <a href="/">← Back to ESPN dashboard</a>
            </div>

        </body>
        </html>
        """,
        games=games,
        leagues=leagues,
    )


# ============================================================
# API ROUTES
# ============================================================

@app.route("/api/dashboard")
def api_dashboard():
    try:
        return jsonify(build_dashboard())
    except Exception as e:
        return jsonify(
            {
                "error": str(e)
            }
        ), 500


# ============================================================
# MAIN DASHBOARD
# ============================================================

HTML = """
<!doctype html>
<html>

<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>Fantasy Dashboard</title>

    <style>
        body {
            background: #111;
            color: #eee;
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 16px;
        }

        .container {
            max-width: 900px;
            margin: auto;
        }

        h1 {
            margin-top: 0;
        }

        .top-links {
            margin-bottom: 15px;
        }

        a {
            color: #7db7ff;
        }

        .card {
            background: #1c1c1c;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 14px;
        }

        .player {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            padding: 10px 0;
            border-bottom: 1px solid #333;
        }

        .player:last-child {
            border-bottom: none;
        }

        .position {
            color: #aaa;
            font-size: 12px;
        }

        .points {
            font-weight: bold;
        }

        button {
            background: #333;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 9px 12px;
            cursor: pointer;
        }

        button:hover {
            background: #444;
        }

        .slate {
            display: inline-block;
            margin: 4px;
        }

        .status {
            color: #aaa;
            font-size: 13px;
        }
    </style>
</head>

<body>

<div class="container">

    <h1>Fantasy Dashboard</h1>

    <div class="top-links">
        <a href="/yahoo">Yahoo Fantasy</a>
    </div>

    <div id="content">
        Loading...
    </div>

</div>

<script>

async function loadDashboard() {

    const content = document.getElementById("content");

    try {

        const response = await fetch("/api/dashboard");

        const data = await response.json();

        if (data.error) {
            content.innerHTML =
                "<div class='card'>Error: " +
                data.error +
                "</div>";

            return;
        }

        let html = "";

        html += `
            <div class="card">
                <h2>${data.league_name}</h2>
                <div class="status">
                    ESPN
                </div>
            </div>
        `;

        html += `
            <div class="card">
                <h3>NFL Slates</h3>
        `;

        for (const slate of data.slates) {

            html += `
                <button class="slate">
                    ${slate.label}
                </button>
            `;
        }

        html += `</div>`;

        if (data.my_team) {

            html += `
                <div class="card">
                    <h2>
                        ${data.my_team.team_name}
                    </h2>
            `;

            for (const player of data.my_team.players) {

                html += `
                    <div class="player">
                        <div>
                            <strong>${player.name}</strong>
                            <div class="position">
                                Position ${player.position ?? ""}
                            </div>
                        </div>

                        <div class="points">
                            ${player.fantasy_points}
                        </div>
                    </div>
                `;
            }

            html += `</div>`;
        }

        if (data.opponent) {

            html += `
                <div class="card">
                    <h2>
                        ${data.opponent.team_name}
                    </h2>
            `;

            for (const player of data.opponent.players) {

                html += `
                    <div class="player">
                        <div>
                            <strong>${player.name}</strong>
                            <div class="position">
                                Position ${player.position ?? ""}
                            </div>
                        </div>

                        <div class="points">
                            ${player.fantasy_points}
                        </div>
                    </div>
                `;
            }

            html += `</div>`;
        }

        content.innerHTML = html;

    } catch (error) {

        content.innerHTML =
            "<div class='card'>Unable to load dashboard.</div>";

    }
}

loadDashboard();

setInterval(loadDashboard, 60000);

</script>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )
