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


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

LOCAL_TIMEZONE = ZoneInfo("America/Chicago")

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32),
)


# ============================================================
# ESPN
# ============================================================

ESPN_SWID = os.getenv("ESPN_SWID")
ESPN_S2 = os.getenv("ESPN_S2")
LEAGUE_ID = os.getenv("ESPN_LEAGUE_ID")
SEASON = os.getenv("ESPN_SEASON", "2026")

MY_OWNER_GUID = "{DE1DCE7E-4046-4158-A37D-10DD7C1923A0}"

ESPN_FANTASY_URL = (
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
    f"seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
)

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/"
    "football/nfl/scoreboard"
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


# ============================================================
# YAHOO
# ============================================================

YAHOO_CLIENT_ID = os.getenv("YAHOO_CLIENT_ID")
YAHOO_CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET")
YAHOO_REDIRECT_URI = os.getenv("YAHOO_REDIRECT_URI")

YAHOO_FANTASY_URL = (
    "https://fantasysports.yahooapis.com/fantasy/v2"
)

YAHOO_AUTH_URL = (
    "https://api.login.yahoo.com/oauth2/request_auth"
)

YAHOO_TOKEN_URL = (
    "https://api.login.yahoo.com/oauth2/get_token"
)


# ============================================================
# SLEEPER
# ============================================================

SLEEPER_USERNAME = os.getenv(
    "SLEEPER_USERNAME",
    "kramps247",
)

SLEEPER_API_URL = (
    "https://api.sleeper.app/v1"
)

# Sleeper tells developers to cache this because the full
# player database is roughly 5 MB and should not be requested
# repeatedly.
SLEEPER_PLAYER_CACHE = None
SLEEPER_PLAYER_CACHE_TIME = 0


# ============================================================
# YAHOO OAUTH
# ============================================================

@app.route("/yahoo/login")
def yahoo_login():

    if not YAHOO_CLIENT_ID:
        return "YAHOO_CLIENT_ID is not configured.", 500

    if not YAHOO_CLIENT_SECRET:
        return "YAHOO_CLIENT_SECRET is not configured.", 500

    if not YAHOO_REDIRECT_URI:
        return "YAHOO_REDIRECT_URI is not configured.", 500

    state = secrets.token_urlsafe(32)

    session["yahoo_oauth_state"] = state

    params = {
        "client_id": YAHOO_CLIENT_ID,
        "redirect_uri": YAHOO_REDIRECT_URI,
        "response_type": "code",
        "state": state,
    }

    return redirect(
        f"{YAHOO_AUTH_URL}?{urlencode(params)}"
    )


@app.route("/yahoo/callback")
def yahoo_callback():

    error = request.args.get("error")

    if error:
        return jsonify({
            "error": error,
            "description": request.args.get(
                "error_description"
            ),
        }), 400

    returned_state = request.args.get("state")

    expected_state = session.pop(
        "yahoo_oauth_state",
        None,
    )

    if (
        not returned_state
        or not expected_state
        or returned_state != expected_state
    ):
        return jsonify({
            "error": "Invalid Yahoo OAuth state."
        }), 400

    code = request.args.get("code")

    if not code:
        return jsonify({
            "error":
                "No Yahoo authorization code received."
        }), 400

    try:
        response = requests.post(
            YAHOO_TOKEN_URL,
            data={
                "grant_type":
                    "authorization_code",
                "redirect_uri":
                    YAHOO_REDIRECT_URI,
                "code":
                    code,
            },
            auth=(
                YAHOO_CLIENT_ID,
                YAHOO_CLIENT_SECRET,
            ),
            timeout=20,
        )
    except requests.RequestException as error:
        return jsonify({
            "error":
                "Could not contact Yahoo token endpoint.",
            "details":
                str(error),
        }), 502

    if not response.ok:
        return jsonify({
            "error":
                "Yahoo token exchange failed.",
            "status_code":
                response.status_code,
            "details":
                response.text,
        }), 400

    try:
        token_data = response.json()
    except ValueError:
        return jsonify({
            "error":
                "Yahoo returned an invalid token response.",
            "details":
                response.text,
        }), 400

    if token_data.get("access_token"):
        session["yahoo_access_token"] = (
            token_data["access_token"]
        )

    if token_data.get("refresh_token"):
        session["yahoo_refresh_token"] = (
            token_data["refresh_token"]
        )

    return redirect("/yahoo")


def get_yahoo_access_token():
    return session.get("yahoo_access_token")


def yahoo_api_request(access_token, path):

    url = (
        f"{YAHOO_FANTASY_URL}/{path}"
    )

    return requests.get(
        url,
        headers={
            "Authorization":
                f"Bearer {access_token}",
            "Accept":
                "application/json",
        },
        params={
            "format":
                "json",
        },
        timeout=20,
    )


def get_yahoo_games():

    access_token = get_yahoo_access_token()

    if not access_token:
        return None

    response = yahoo_api_request(
        access_token,
        "users;use_login=1/"
        "games;game_codes=nfl",
    )

    if response.status_code != 200:
        return {
            "error": True,
            "status_code":
                response.status_code,
            "message":
                response.text,
        }

    try:
        return response.json()
    except ValueError:
        return {
            "error": True,
            "status_code":
                response.status_code,
            "message":
                "Yahoo returned a non-JSON response.",
            "raw":
                response.text,
        }


def get_yahoo_leagues():

    access_token = get_yahoo_access_token()

    if not access_token:
        return None

    response = yahoo_api_request(
        access_token,
        "users;use_login=1/"
        "games;game_codes=nfl/"
        "leagues",
    )

    if response.status_code != 200:
        return {
            "error": True,
            "status_code":
                response.status_code,
            "message":
                response.text,
        }

    try:
        return response.json()
    except ValueError:
        return {
            "error": True,
            "status_code":
                response.status_code,
            "message":
                "Yahoo returned a non-JSON response.",
            "raw":
                response.text,
        }


@app.route("/yahoo")
def yahoo_page():

    access_token = get_yahoo_access_token()

    if not access_token:
        return render_template_string(
            """
            <!doctype html>
            <html>
            <head>
                <meta
                    name="viewport"
                    content="width=device-width, initial-scale=1"
                >
                <title>Yahoo Fantasy</title>
                <style>
                    body {
                        background:#111;
                        color:#eee;
                        font-family:Arial,sans-serif;
                        padding:30px;
                    }
                    a { color:#7db7ff; }
                    .card {
                        background:#1d1d1d;
                        border-radius:12px;
                        padding:20px;
                        margin-bottom:15px;
                    }
                </style>
            </head>
            <body>

                <div class="card">
                    <h1>Yahoo Fantasy</h1>
                    <p>
                        You are not currently authenticated
                        with Yahoo.
                    </p>
                    <a href="/yahoo/login">
                        Connect Yahoo
                    </a>
                </div>

                <div class="card">
                    <a href="/">
                        ← Back to dashboard
                    </a>
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
            <meta
                name="viewport"
                content="width=device-width, initial-scale=1"
            >
            <title>Yahoo Fantasy</title>
            <style>
                body {
                    background:#111;
                    color:#eee;
                    font-family:Arial,sans-serif;
                    padding:20px;
                    max-width:900px;
                    margin:auto;
                }
                .card {
                    background:#1d1d1d;
                    border-radius:12px;
                    padding:18px;
                    margin-bottom:15px;
                }
                .success { color:#65d98b; }
                .error { color:#ff7777; }
                pre {
                    white-space:pre-wrap;
                    word-break:break-word;
                    background:#0b0b0b;
                    padding:12px;
                    border-radius:8px;
                }
                a { color:#7db7ff; }
            </style>
        </head>

        <body>

            <h1>Yahoo Fantasy</h1>

            <div class="card">
                <h2 class="success">
                    ✓ Yahoo authentication successful
                </h2>
                <p>
                    Your app successfully received
                    a Yahoo OAuth access token.
                </p>
            </div>

            <div class="card">
                <h2>NFL Fantasy Games</h2>

                {% if games and games.error %}
                    <p class="error">
                        Yahoo Fantasy API returned an error:
                    </p>
                    <pre>
{{ games | tojson(indent=2) }}
                    </pre>

                {% elif games %}
                    <p class="success">
                        ✓ Yahoo Fantasy API responded
                    </p>
                    <pre>
{{ games | tojson(indent=2) }}
                    </pre>

                {% else %}
                    <p>No game data returned.</p>
                {% endif %}
            </div>

            <div class="card">
                <h2>Your Yahoo Fantasy Leagues</h2>

                {% if leagues and leagues.error %}
                    <p class="error">
                        Yahoo Fantasy League API
                        returned an error:
                    </p>
                    <pre>
{{ leagues | tojson(indent=2) }}
                    </pre>

                {% elif leagues %}
                    <p class="success">
                        ✓ League data returned
                    </p>
                    <pre>
{{ leagues | tojson(indent=2) }}
                    </pre>

                {% else %}
                    <p>No league data returned.</p>
                {% endif %}
            </div>

            <div class="card">
                <a href="/">
                    ← Back to dashboard
                </a>
            </div>

        </body>
        </html>
        """,
        games=games,
        leagues=leagues,
    )


# ============================================================
# SLEEPER API HELPERS
# ============================================================

def sleeper_get(path):

    response = requests.get(
        f"{SLEEPER_API_URL}/{path}",
        timeout=20,
    )

    response.raise_for_status()

    return response.json()


def get_sleeper_user():

    return sleeper_get(
        f"user/{SLEEPER_USERNAME}"
    )


def get_sleeper_leagues(user_id):

    return sleeper_get(
        f"user/{user_id}/leagues/nfl/{SEASON}"
    )


def get_sleeper_state():

    return sleeper_get(
        "state/nfl"
    )


def get_sleeper_league(league_id):

    return sleeper_get(
        f"league/{league_id}"
    )


def get_sleeper_rosters(league_id):

    return sleeper_get(
        f"league/{league_id}/rosters"
    )


def get_sleeper_users(league_id):

    return sleeper_get(
        f"league/{league_id}/users"
    )


def get_sleeper_matchups(
    league_id,
    week,
):

    return sleeper_get(
        f"league/{league_id}/matchups/{week}"
    )


def get_sleeper_players():

    global SLEEPER_PLAYER_CACHE
    global SLEEPER_PLAYER_CACHE_TIME

    now = time.time()

    # Cache for 24 hours.
    if (
        SLEEPER_PLAYER_CACHE is not None
        and
        now - SLEEPER_PLAYER_CACHE_TIME
        < 86400
    ):
        return SLEEPER_PLAYER_CACHE

    players = sleeper_get(
        "players/nfl"
    )

    SLEEPER_PLAYER_CACHE = players
    SLEEPER_PLAYER_CACHE_TIME = now

    return players


def choose_sleeper_league(
    leagues
):

    if not leagues:
        raise RuntimeError(
            "No 2026 Sleeper NFL leagues found."
        )

    # Prefer an active league.
    for league in leagues:
        if league.get("status") == "in_season":
            return league

    # Otherwise use the first 2026 league.
    return leagues[0]


def sleeper_team_name(
    roster_id,
    users,
):

    for user in users:

        # Sleeper's users endpoint associates users
        # with their roster through user_id.
        #
        # We resolve the owner using the roster separately
        # in build_sleeper_matchup.
        pass

    return f"Roster {roster_id}"


def get_sleeper_team_label(
    roster,
    users,
):

    owner_id = roster.get(
        "owner_id"
    )

    for user in users:

        if user.get(
            "user_id"
        ) == owner_id:

            metadata = user.get(
                "metadata",
                {}
            ) or {}

            team_name = metadata.get(
                "team_name"
            )

            if team_name:
                return team_name

            return (
                user.get("display_name")
                or user.get("username")
                or f"Roster {roster['roster_id']}"
            )

    return f"Roster {roster['roster_id']}"


def sleeper_position(
    player
):

    positions = player.get(
        "fantasy_positions"
    ) or []

    if positions:
        return positions[0]

    return player.get(
        "position"
    ) or ""


def build_sleeper_players(
    matchup,
    players,
):

    output = []

    starters = matchup.get(
        "starters",
        []
    )

    for index, player_id in enumerate(
        starters
    ):

        player_id = str(player_id)

        player = players.get(
            player_id
        )

        # D/ST entries such as "KC" are not always
        # represented as normal player objects.
        if not player:

            output.append({
                "name":
                    f"{player_id} D/ST",
                "slot":
                    "D/ST",
                "player_id":
                    player_id,
                "nfl_team":
                    player_id,
                "opponent":
                    "",
                "game_time":
                    "",
                "points":
                    None,
                "injury":
                    "",
                "status":
                    "PROJECTED",
                "pro_team_id":
                    player_id,
            })

            continue

        team = player.get(
            "team"
        ) or ""

        output.append({

            "name":
                (
                    player.get("full_name")
                    or
                    (
                        f"{player.get('first_name', '')} "
                        f"{player.get('last_name', '')}"
                    ).strip()
                ),

            "slot":
                sleeper_position(player),

            "player_id":
                player_id,

            "nfl_team":
                team,

            "opponent":
                "",

            "game_time":
                "",

            "points":
                None,

            "injury":
                player.get(
                    "injury_status"
                ) or "",

            "status":
                "PROJECTED",

            "pro_team_id":
                team,
        })

    return output


def build_sleeper_matchup():

    user = get_sleeper_user()

    if not user:
        raise RuntimeError(
            f"Sleeper user '{SLEEPER_USERNAME}' was not found."
        )

    user_id = user.get(
        "user_id"
    )

    leagues = get_sleeper_leagues(
        user_id
    )

    league = choose_sleeper_league(
        leagues
    )

    league_id = league[
        "league_id"
    ]

    state = get_sleeper_state()

    week = state.get(
        "display_week"
    ) or state.get(
        "week"
    )

    rosters = get_sleeper_rosters(
        league_id
    )

    users = get_sleeper_users(
        league_id
    )

    matchups = get_sleeper_matchups(
        league_id,
        week,
    )

    my_roster = None

    for roster in rosters:

        if roster.get(
            "owner_id"
        ) == user_id:

            my_roster = roster
            break

    if not my_roster:

        raise RuntimeError(
            "Could not find your Sleeper roster."
        )

    my_roster_id = my_roster[
        "roster_id"
    ]

    my_matchup = None

    for matchup in matchups:

        if matchup.get(
            "roster_id"
        ) == my_roster_id:

            my_matchup = matchup
            break

    if not my_matchup:

        raise RuntimeError(
            "Could not find your current Sleeper matchup."
        )

    matchup_id = my_matchup.get(
        "matchup_id"
    )

    opponent_matchup = None

    for matchup in matchups:

        if (
            matchup.get("matchup_id")
            == matchup_id
            and
            matchup.get("roster_id")
            != my_roster_id
        ):

            opponent_matchup = matchup
            break

    # Some league formats may have no opponent yet.
    if not opponent_matchup:

        opponent_matchup = {
            "roster_id": None,
            "starters": [],
            "points": 0,
        }

    roster_by_id = {
        roster["roster_id"]:
            roster
        for roster in rosters
    }

    players = get_sleeper_players()

    my_players = build_sleeper_players(
        my_matchup,
        players,
    )

    opponent_players = build_sleeper_players(
        opponent_matchup,
        players,
    )

    my_roster_name = get_sleeper_team_label(
        my_roster,
        users,
    )

    opponent_roster = roster_by_id.get(
        opponent_matchup.get(
            "roster_id"
        )
    )

    if opponent_roster:
        opponent_name = get_sleeper_team_label(
            opponent_roster,
            users,
        )
    else:
        opponent_name = "Opponent"

    return {

        "platform":
            "Sleeper",

        "league_name":
            league.get(
                "name",
                "Sleeper",
            ),

        "week":
            week,

        "user":
            user.get(
                "display_name"
                or "username"
            ),

        "my_team": {

            "id":
                my_roster_id,

            "name":
                my_roster_name,

            "abbrev":
                my_roster_name,

            "league":
                "Sleeper",

            "theme":
                "sleeper",

            "total":
                float(
                    my_matchup.get(
                        "points"
                    ) or 0
                ),

            "players":
                my_players,
        },

        "opponent": {

            "id":
                opponent_matchup.get(
                    "roster_id"
                ),

            "name":
                opponent_name,

            "abbrev":
                opponent_name,

            "league":
                "Sleeper",

            "theme":
                "sleeper",

            "total":
                float(
                    opponent_matchup.get(
                        "points"
                    ) or 0
                ),

            "players":
                opponent_players,
        },
    }


# ============================================================
# NFL SCHEDULE
# ============================================================

def get_nfl_schedule():

    today = datetime.now(
        LOCAL_TIMEZONE
    ).date()

    games = []

    for day_offset in range(0, 8):

        date = today + timedelta(
            days=day_offset
        )

        date_string = date.strftime(
            "%Y%m%d"
        )

        response = requests.get(
            ESPN_SCOREBOARD_URL,
            params={
                "dates":
                    date_string
            },
            timeout=20,
        )

        response.raise_for_status()

        scoreboard = response.json()

        for event in scoreboard.get(
            "events",
            []
        ):

            competitions = event.get(
                "competitions",
                []
            )

            if not competitions:
                continue

            competition = competitions[0]

            competitors = competition.get(
                "competitors",
                []
            )

            if len(competitors) < 2:
                continue

            home = None
            away = None

            for competitor in competitors:

                team = competitor.get(
                    "team",
                    {}
                )

                team_data = {

                    "id":
                        str(
                            team.get("id")
                        ),

                    "abbreviation":
                        team.get(
                            "abbreviation"
                        ),

                    "display_name":
                        team.get(
                            "displayName"
                        ),
                }

                if competitor.get(
                    "homeAway"
                ) == "home":

                    home = team_data

                else:

                    away = team_data

            if not home or not away:
                continue

            kickoff_raw = (
                competition.get("date")
                or event.get("date")
            )

            if not kickoff_raw:
                continue

            try:

                kickoff = datetime.fromisoformat(
                    kickoff_raw.replace(
                        "Z",
                        "+00:00"
                    )
                )

            except ValueError:
                continue

            status = competition.get(
                "status",
                {}
            )

            type_data = status.get(
                "type",
                {}
            )

            games.append({

                "id":
                    event.get("id"),

                "kickoff":
                    kickoff,

                "home":
                    home,

                "away":
                    away,

                "status":
                    type_data.get(
                        "name"
                    ),

                "status_detail":
                    type_data.get(
                        "detail"
                    ),
            })

    return games


# ============================================================
# SLATES
# ============================================================

def group_games_into_slates(games):

    if not games:
        return []

    games = sorted(
        games,
        key=lambda game:
            game["kickoff"]
    )

    slates = []

    for game in games:

        if not slates:

            slates.append({
                "kickoff":
                    game["kickoff"],
                "games":
                    [game],
            })

            continue

        current_slate = slates[-1]

        difference = (
            game["kickoff"]
            - current_slate["kickoff"]
        ).total_seconds()

        if difference <= 45 * 60:

            current_slate["games"].append(
                game
            )

        else:

            slates.append({
                "kickoff":
                    game["kickoff"],
                "games":
                    [game],
            })

    return slates


def format_slate_label(kickoff):

    local_kickoff = kickoff.astimezone(
        LOCAL_TIMEZONE
    )

    now = datetime.now(
        LOCAL_TIMEZONE
    )

    today = now.date()

    tomorrow = today + timedelta(
        days=1
    )

    if local_kickoff.date() == today:
        day_name = "Today"

    elif local_kickoff.date() == tomorrow:
        day_name = "Tomorrow"

    else:
        day_name = local_kickoff.strftime(
            "%A"
        )

    if os.name == "nt":

        time_string = local_kickoff.strftime(
            "%#I:%M %p"
        )

    else:

        time_string = local_kickoff.strftime(
            "%-I:%M %p"
        )

    return f"{day_name} {time_string}"


def format_game_time(kickoff):

    local_kickoff = kickoff.astimezone(
        LOCAL_TIMEZONE
    )

    if os.name == "nt":

        return local_kickoff.strftime(
            "%#I:%M %p"
        )

    return local_kickoff.strftime(
        "%-I:%M %p"
    )


def build_slate_data(games):

    slates = group_games_into_slates(
        games
    )

    output = []

    now = datetime.now(
        timezone.utc
    )

    for index, slate in enumerate(
        slates
    ):

        kickoff = slate["kickoff"]

        local_kickoff = kickoff.astimezone(
            LOCAL_TIMEZONE
        )

        output.append({

            "id":
                index,

            "label":
                format_slate_label(
                    kickoff
                ),

            "date":
                local_kickoff.date().isoformat(),

            "kickoff":
                local_kickoff.isoformat(),

            "timestamp":
                kickoff.timestamp(),

            "is_upcoming":
                kickoff > now,

            "games": [

                {

                    "id":
                        game["id"],

                    "away":
                        game["away"][
                            "abbreviation"
                        ],

                    "home":
                        game["home"][
                            "abbreviation"
                        ],

                    "away_id":
                        game["away"]["id"],

                    "home_id":
                        game["home"]["id"],

                    "kickoff":
                        game["kickoff"]
                            .astimezone(
                                LOCAL_TIMEZONE
                            )
                            .isoformat(),

                    "game_time":
                        format_game_time(
                            game["kickoff"]
                        ),
                }

                for game in slate["games"]
            ],
        })

    return output


def get_next_slate_index(slates):

    now = datetime.now(
        timezone.utc
    )

    for slate in slates:

        kickoff = datetime.fromtimestamp(
            slate["timestamp"],
            tz=timezone.utc,
        )

        if kickoff > now:
            return slate["id"]

    return None


# ============================================================
# ESPN FANTASY DATA
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


def find_my_team(data):

    for team in data["teams"]:

        if MY_OWNER_GUID in team.get(
            "owners",
            []
        ):

            return team

    raise RuntimeError(
        "Could not find your ESPN team."
    )


def find_matchup(data, my_team):

    current_period = data[
        "scoringPeriodId"
    ]

    opponent_id = None

    for game in data["schedule"]:

        if game.get(
            "matchupPeriodId"
        ) != current_period:

            continue

        home = game.get(
            "home",
            {}
        )

        away = game.get(
            "away",
            {}
        )

        if home.get(
            "teamId"
        ) == my_team["id"]:

            opponent_id = away.get(
                "teamId"
            )

            break

        if away.get(
            "teamId"
        ) == my_team["id"]:

            opponent_id = home.get(
                "teamId"
            )

            break

    if opponent_id is None:

        raise RuntimeError(
            "Could not find current matchup."
        )

    for team in data["teams"]:

        if team["id"] == opponent_id:
            return team

    raise RuntimeError(
        "Could not find opponent team."
    )


# ============================================================
# ESPN LINEUP
# ============================================================

SLOT_NAMES = {
    0: "QB",
    2: "RB",
    4: "WR",
    6: "TE",
    16: "D/ST",
    17: "K",
    23: "FLEX",
}

LINEUP_ORDER = [
    "QB",
    "RB",
    "WR",
    "TE",
    "FLEX",
    "K",
    "D/ST",
]


def get_players(team):

    players = []

    roster = team.get(
        "roster",
        {}
    )

    for entry in roster.get(
        "entries",
        []
    ):

        slot_id = entry.get(
            "lineupSlotId"
        )

        player_pool_entry = entry.get(
            "playerPoolEntry",
            {}
        )

        player = player_pool_entry.get(
            "player",
            {}
        )

        players.append({

            "player_id":
                entry.get(
                    "playerId"
                ),

            "name":
                player.get(
                    "fullName"
                ),

            "slot_id":
                slot_id,

            "slot":
                SLOT_NAMES.get(
                    slot_id,
                    "BENCH"
                ),

            "starter":
                slot_id in SLOT_NAMES,

            "injury_status":
                player.get(
                    "injuryStatus"
                ),

            "pro_team_id":
                str(
                    player.get(
                        "proTeamId"
                    )
                )
                if player.get(
                    "proTeamId"
                ) is not None
                else None,
        })

    return players


def get_starters(players):

    starters = [
        player
        for player in players
        if player["starter"]
    ]

    players_by_slot = {}

    for player in starters:

        slot = player["slot"]

        if slot not in players_by_slot:
            players_by_slot[slot] = []

        players_by_slot[slot].append(
            player
        )

    ordered = []

    for slot in LINEUP_ORDER:

        ordered.extend(
            players_by_slot.get(
                slot,
                []
            )
        )

    return ordered


# ============================================================
# ESPN PLAYER STATS
# ============================================================

def find_player_objects(data, player_id):

    found = []

    def search(obj):

        if isinstance(obj, dict):

            if obj.get("id") == player_id:
                found.append(obj)

            for value in obj.values():
                search(value)

        elif isinstance(obj, list):

            for value in obj:
                search(value)

    search(data)

    return found


def get_player_stats(data, player_id):

    current_period = data[
        "scoringPeriodId"
    ]

    projections = []
    actuals = []

    for player in find_player_objects(
        data,
        player_id,
    ):

        stats = player.get(
            "stats",
            []
        )

        if not isinstance(stats, list):
            continue

        for record in stats:

            if not isinstance(
                record,
                dict
            ):
                continue

            if record.get(
                "seasonId"
            ) != int(SEASON):
                continue

            if record.get(
                "scoringPeriodId"
            ) != current_period:
                continue

            if (
                record.get("statSourceId") == 1
                and
                record.get("statSplitTypeId") == 1
            ):

                applied_total = record.get(
                    "appliedTotal"
                )

                if applied_total is not None:
                    projections.append(
                        float(applied_total)
                    )

            if (
                record.get("statSourceId") == 0
                and
                record.get("statSplitTypeId") == 1
            ):

                applied_total = record.get(
                    "appliedTotal"
                )

                if applied_total is not None:
                    actuals.append(
                        float(applied_total)
                    )

    projection = (
        projections[0]
        if projections
        else None
    )

    actual = (
        actuals[0]
        if actuals
        else None
    )

    return projection, actual


def get_player_score(data, player):

    projection, actual = get_player_stats(
        data,
        player["player_id"],
    )

    if actual is not None:

        return {
            "points":
                actual,
            "projected":
                projection,
            "actual":
                actual,
            "status":
                "LOCKED",
        }

    return {
        "points":
            projection,
        "projected":
            projection,
        "actual":
            None,
        "status":
            "PROJECTED",
    }


# ============================================================
# ESPN GAME LOOKUP
# ============================================================

def build_game_lookup(nfl_games):

    lookup = {}

    for game in nfl_games:

        home_id = str(
            game["home"]["id"]
        )

        away_id = str(
            game["away"]["id"]
        )

        local_kickoff = (
            game["kickoff"]
            .astimezone(
                LOCAL_TIMEZONE
            )
        )

        lookup[home_id] = {
            "team":
                game["home"]["abbreviation"],
            "opponent":
                game["away"]["abbreviation"],
            "opponent_id":
                away_id,
            "home":
                True,
            "kickoff":
                local_kickoff,
            "game_time":
                format_game_time(
                    game["kickoff"]
                ),
            "game_status":
                game["status"],
            "status_detail":
                game["status_detail"],
        }

        lookup[away_id] = {
            "team":
                game["away"]["abbreviation"],
            "opponent":
                game["home"]["abbreviation"],
            "opponent_id":
                home_id,
            "home":
                False,
            "kickoff":
                local_kickoff,
            "game_time":
                format_game_time(
                    game["kickoff"]
                ),
            "game_status":
                game["status"],
            "status_detail":
                game["status_detail"],
        }

    return lookup


def get_player_game_info(
    player,
    game_lookup,
):

    team_id = player.get(
        "pro_team_id"
    )

    if not team_id:

        return {
            "team": "",
            "opponent": "",
            "game_time": "",
            "game_status": "",
        }

    game = game_lookup.get(
        str(team_id)
    )

    if not game:

        return {
            "team": "",
            "opponent": "",
            "game_time": "",
            "game_status": "",
        }

    return {
        "team":
            game["team"],
        "opponent":
            game["opponent"],
        "game_time":
            game["game_time"],
        "game_status":
            game["game_status"],
    }


def build_team_data(
    team,
    players,
    data,
    game_lookup,
):

    starters = get_starters(
        players
    )

    output_players = []

    total = 0.0

    for player in starters:

        score = get_player_score(
            data,
            player,
        )

        points = score["points"]

        if points is not None:
            total += points

        injury = (
            player["injury_status"]
            or ""
        )

        game_info = get_player_game_info(
            player,
            game_lookup,
        )

        output_players.append({

            "name":
                player["name"],

            "slot":
                player["slot"],

            "points":
                points,

            "projected":
                score["projected"],

            "actual":
                score["actual"],

            "status":
                score["status"],

            "injury":
                injury,

            "pro_team_id":
                player["pro_team_id"],

            "nfl_team":
                game_info["team"],

            "opponent":
                game_info["opponent"],

            "game_time":
                game_info["game_time"],

            "game_status":
                game_info["game_status"],
        })

    return {

        "id":
            team["id"],

        "name":
            team["name"],

        "abbrev":
            team["abbrev"],

        "league":
            "ESPN",

        "theme":
            "espn",

        "players":
            output_players,

        "total":
            total,
    }


def build_espn_matchup(
    nfl_games,
):

    fantasy_data = get_league_data()

    current_period = fantasy_data[
        "scoringPeriodId"
    ]

    my_team = find_my_team(
        fantasy_data
    )

    opponent = find_matchup(
        fantasy_data,
        my_team,
    )

    game_lookup = build_game_lookup(
        nfl_games
    )

    my_data = build_team_data(
        my_team,
        get_players(my_team),
        fantasy_data,
        game_lookup,
    )

    opponent_data = build_team_data(
        opponent,
        get_players(opponent),
        fantasy_data,
        game_lookup,
    )

    return {

        "platform":
            "ESPN",

        "week":
            current_period,

        "my_team":
            my_data,

        "opponent":
            opponent_data,

        "difference":
            my_data["total"]
            - opponent_data["total"],
    }


# ============================================================
# UNIFIED DASHBOARD API
# ============================================================

@app.route("/api/dashboard")
def api_dashboard():

    try:

        nfl_games = get_nfl_schedule()

        slates = build_slate_data(
            nfl_games
        )

        next_slate_id = (
            get_next_slate_index(
                slates
            )
        )

        sleeper_error = None
        espn_error = None

        try:
            sleeper = build_sleeper_matchup()
        except Exception as error:
            sleeper = None
            sleeper_error = str(error)

        try:
            espn = build_espn_matchup(
                nfl_games
            )
        except Exception as error:
            espn = None
            espn_error = str(error)

        yahoo_connected = bool(
            get_yahoo_access_token()
        )

        return jsonify({

            "updated":
                time.strftime(
                    "%I:%M:%S %p"
                ),

            "slates":
                slates,

            "next_slate_id":
                next_slate_id,

            "sleeper":
                sleeper,

            "sleeper_error":
                sleeper_error,

            "yahoo": {

                "connected":
                    yahoo_connected,

                "status":
                    "Fantasy API access pending"
                    if yahoo_connected
                    else
                    "Not connected",
            },

            "espn":
                espn,

            "espn_error":
                espn_error,
        })

    except Exception as error:

        return jsonify({
            "error":
                str(error)
        }), 500


# ============================================================
# HOME PAGE
# ============================================================

HTML = r"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
    Fantasy Dashboard
</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #111;

    color: #f5f5f5;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        Arial,
        sans-serif;
}

.container {

    width: 100%;

    max-width: 1100px;

    margin: 0 auto;

    padding: 14px;
}

.header {

    text-align: center;

    padding: 12px 0 18px;
}

.title {

    font-size: 24px;

    font-weight: 800;

    letter-spacing: 1px;
}

.subtitle {

    color: #999;

    font-size: 13px;

    margin-top: 4px;
}


/* ============================================================
   SLATES
   ============================================================ */

.slate-card {

    background: #1d1d1d;

    border-radius: 18px;

    padding: 16px 18px;

    margin-bottom: 14px;
}

.slate-label {

    color: #888;

    font-size: 10px;

    font-weight: 800;

    letter-spacing: 1px;

    text-transform: uppercase;

    margin-bottom: 10px;
}

.slate-options {

    display: flex;

    flex-wrap: wrap;

    gap: 8px;
}

.slate-option {

    position: relative;
}

.slate-option input {

    position: absolute;

    opacity: 0;

    pointer-events: none;
}

.slate-option label {

    display: block;

    background: #292929;

    border: 1px solid #333;

    border-radius: 10px;

    padding: 10px 12px;

    cursor: pointer;

    font-size: 12px;

    font-weight: 700;
}

.slate-option input:checked + label {

    background: #3a3a3a;

    border-color: #777;
}

.slate-games {

    color: #888;

    font-size: 10px;

    margin-top: 5px;

    font-weight: 500;
}


/* ============================================================
   REFRESH
   ============================================================ */

.refresh-row {

    display: flex;

    justify-content: space-between;

    align-items: center;

    margin-bottom: 14px;
}

.updated {

    color: #777;

    font-size: 12px;
}

.refresh {

    border: 0;

    border-radius: 10px;

    padding: 9px 14px;

    background: #2b2b2b;

    color: white;

    font-weight: 700;

    cursor: pointer;
}


/* ============================================================
   LEAGUE SECTION
   ============================================================ */

.league-section {

    margin-bottom: 24px;
}

.league-title {

    font-size: 17px;

    font-weight: 800;

    margin: 10px 4px;
}

.league-subtitle {

    color: #777;

    font-size: 11px;

    margin: -6px 4px 10px;
}


/* ============================================================
   SCORE
   ============================================================ */

.score-card {

    background: #1d1d1d;

    border-radius: 18px;

    padding: 18px;

    margin-bottom: 10px;
}

.matchup {

    display: grid;

    grid-template-columns:
        1fr auto 1fr;

    align-items: center;

    text-align: center;

    gap: 10px;
}

.team-abbrev {

    font-size: 17px;

    font-weight: 800;
}

.score {

    font-size: 30px;

    font-weight: 800;

    margin-top: 5px;
}

.vs {

    color: #777;

    font-size: 12px;

    font-weight: 700;
}


/* ============================================================
   ROSTERS
   ============================================================ */

.rosters {

    display: grid;

    grid-template-columns:
        1fr 1fr;

    gap: 12px;
}

.team-card {

    background: #1d1d1d;

    border-radius: 18px;

    overflow: hidden;

    border-top: 3px solid #555;
}

.team-header {

    padding: 14px;

    display: flex;

    justify-content: space-between;

    align-items: center;

    border-bottom: 1px solid #303030;
}

.team-name {

    font-weight: 800;

    font-size: 16px;
}

.team-total {

    font-size: 18px;

    font-weight: 800;
}


/* ============================================================
   PLAYER
   ============================================================ */

.player {

    display: grid;

    grid-template-columns:
        42px 1fr auto;

    align-items: center;

    gap: 8px;

    padding: 12px 14px;

    border-bottom: 1px solid #292929;
}

.player:last-child {

    border-bottom: 0;
}

.position {

    color: #888;

    font-size: 11px;

    font-weight: 800;
}

.player-name {

    font-size: 14px;

    font-weight: 600;
}

.player-meta {

    margin-top: 4px;

    display: flex;

    gap: 7px;

    align-items: center;

    flex-wrap: wrap;
}

.game-info {

    color: #8f8f8f;

    font-size: 10px;

    font-weight: 600;
}

.status {

    font-size: 9px;

    font-weight: 800;
}

.locked {

    color: #7fdc9a;
}

.projected {

    color: #888;
}

.injury {

    font-size: 9px;

    font-weight: 800;

    color: #e6b35a;
}

.injury-alert {

    color: #e86c6c;
}

.points {

    text-align: right;

    font-size: 15px;

    font-weight: 800;
}

.points-label {

    color: #777;

    font-size: 8px;
}


/* ============================================================
   SPECIAL CARDS
   ============================================================ */

.pending {

    background: #1d1d1d;

    border-radius: 18px;

    padding: 20px;

    color: #aaa;

    font-size: 13px;

    line-height: 1.5;
}

.pending strong {

    color: #eee;
}

.error {

    background: #351c1c;

    color: #ff9d9d;

    padding: 15px;

    border-radius: 12px;

    font-size: 13px;

    white-space: pre-wrap;
}

.no-players {

    padding: 20px;

    text-align: center;

    color: #777;

    font-size: 12px;
}

@media (max-width: 700px) {

    .container {
        padding: 10px;
    }

    .rosters {
        grid-template-columns: 1fr;
        gap: 8px;
    }

    .slate-options {
        display: grid;
        grid-template-columns:
            repeat(2, 1fr);
    }

    .slate-option label {
        text-align: center;
        min-height: 42px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
    }
}

</style>

</head>


<body>

<div class="container">

    <div class="header">

        <div class="title">
            FANTASY DASHBOARD
        </div>

        <div class="subtitle">
            All leagues · One NFL slate
        </div>

    </div>


    <div id="content">
        <div class="pending">
            Loading fantasy leagues...
        </div>
    </div>

</div>


<script>

let dashboardData = null;

let selectedSlates = new Set();


async function loadDashboard() {

    const content =
        document.getElementById("content");

    try {

        const response =
            await fetch(
                "/api/dashboard",
                {
                    cache: "no-store"
                }
            );

        const data =
            await response.json();

        if (!response.ok) {

            throw new Error(
                data.error ||
                "Dashboard error"
            );
        }

        dashboardData = data;

        initializeSelectedSlates();

        renderDashboard();

    } catch (error) {

        content.innerHTML = `

            <div class="error">

                ${escapeHtml(
                    error.message
                )}

            </div>

        `;
    }
}


function initializeSelectedSlates() {

    if (

        selectedSlates.size === 0

        &&

        dashboardData.next_slate_id !== null

    ) {

        selectedSlates.add(
            dashboardData.next_slate_id
        );
    }
}


function toggleSlate(
    slateId
) {

    if (
        selectedSlates.has(slateId)
    ) {

        selectedSlates.delete(slateId);

    } else {

        selectedSlates.add(slateId);
    }

    renderDashboard();
}


function renderDashboard() {

    const content =
        document.getElementById(
            "content"
        );

    content.innerHTML = `

        ${renderSlateSelector()}

        <div class="refresh-row">

            <div class="updated">

                Updated
                ${escapeHtml(
                    dashboardData.updated
                )}

            </div>

            <button
                class="refresh"
                onclick="refreshDashboard()"
            >
                ↻ Refresh
            </button>

        </div>

        ${renderSleeper()}

        ${renderYahoo()}

        ${renderESPN()}

    `;
}


/* ============================================================
   SLATE SELECTOR
   ============================================================ */

function renderSlateSelector() {

    if (
        !dashboardData.slates
        ||
        dashboardData.slates.length === 0
    ) {

        return "";
    }

    const options =
        dashboardData.slates
            .map(slate => {

                const checked =
                    selectedSlates.has(
                        slate.id
                    )
                    ? "checked"
                    : "";

                const games =
                    slate.games
                        .map(
                            game =>
                                `${game.away}@${game.home}`
                        )
                        .join(" · ");

                return `

                    <div
                        class="slate-option"
                    >

                        <input
                            type="checkbox"
                            id="slate-${slate.id}"
                            ${checked}
                            onchange="
                                toggleSlate(
                                    ${slate.id}
                                )
                            "
                        >

                        <label
                            for="slate-${slate.id}"
                        >

                            <div>
                                ${escapeHtml(
                                    slate.label
                                )}
                            </div>

                            <div
                                class="slate-games"
                            >
                                ${escapeHtml(
                                    games
                                )}
                            </div>

                        </label>

                    </div>

                `;
            })
            .join("");

    return `

        <div class="slate-card">

            <div class="slate-label">
                NFL SLATES
            </div>

            <div class="slate-options">
                ${options}
            </div>

        </div>

    `;
}


/* ============================================================
   SLATE FILTER
   ============================================================ */

function playerBelongsToSelectedSlate(
    player
) {

    if (
        selectedSlates.size === 0
    ) {
        return false;
    }

    if (!player.pro_team_id) {
        return false;
    }

    const team =
        String(
            player.pro_team_id
        );

    for (
        const slateId
        of selectedSlates
    ) {

        const slate =
            dashboardData.slates.find(
                item =>
                    item.id === slateId
            );

        if (!slate) {
            continue;
        }

        for (
            const game
            of slate.games
        ) {

            /*
             * ESPN uses numeric NFL team IDs.
             * Sleeper uses abbreviations.
             *
             * We therefore check both forms.
             */

            if (
                String(game.home_id)
                    === team
                ||
                String(game.away_id)
                    === team
                ||
                game.home
                    === team
                ||
                game.away
                    === team
            ) {

                return true;
            }
        }
    }

    return false;
}


function getSleeperPlayerTeam(
    player
) {

    return player.nfl_team || "";
}


/* ============================================================
   SLEEPER
   ============================================================ */

function renderSleeper() {

    const sleeper =
        dashboardData.sleeper;

    if (!sleeper) {

        return `

            <div class="league-section">

                <div class="league-title">
                    SLEEPER
                </div>

                <div class="error">

                    ${escapeHtml(
                        dashboardData.sleeper_error
                        ||
                        "Sleeper data unavailable."
                    )}

                </div>

            </div>

        `;
    }

    return renderLeagueSection(
        "SLEEPER",
        sleeper,
        "Sleeper"
    );
}


/* ============================================================
   YAHOO
   ============================================================ */

function renderYahoo() {

    return `

        <div class="league-section">

            <div class="league-title">
                YAHOO
            </div>

            <div class="pending">

                <strong>
                    Yahoo Fantasy API access pending
                </strong>

                <br><br>

                Yahoo OAuth is connected, but Yahoo has
                not yet granted this application access
                to the Fantasy Sports API.

                <br><br>

                Once Yahoo approves the application,
                this section will be populated without
                changing the dashboard layout.

                <br><br>

                <a
                    href="/yahoo"
                    style="color:#7db7ff"
                >
                    View Yahoo connection status →
                </a>

                <br><br>

                <small>
                    Fantasy data provided by Yahoo Fantasy.
                </small>

            </div>

        </div>

    `;
}


/* ============================================================
   ESPN
   ============================================================ */

function renderESPN() {

    const espn =
        dashboardData.espn;

    if (!espn) {

        return `

            <div class="league-section">

                <div class="league-title">
                    ESPN
                </div>

                <div class="error">

                    ${escapeHtml(
                        dashboardData.espn_error
                        ||
                        "ESPN data unavailable."
                    )}

                </div>

            </div>

        `;
    }

    return renderLeagueSection(
        "ESPN",
        espn,
        "ESPN"
    );
}


/* ============================================================
   GENERIC LEAGUE RENDERER
   ============================================================ */

function renderLeagueSection(
    title,
    league,
    platform
) {

    const my =
        league.my_team;

    const opponent =
        league.opponent;

    return `

        <div class="league-section">

            <div class="league-title">
                ${escapeHtml(title)}
            </div>

            <div class="league-subtitle">

                ${escapeHtml(
                    league.league_name
                    ||
                    (
                        platform === "ESPN"
                        ? `Week ${league.week}`
                        : `Week ${league.week}`
                    )
                )}

            </div>

            <div class="score-card">

                <div class="matchup">

                    <div>

                        <div class="team-abbrev">

                            ${escapeHtml(
                                my.abbrev
                            )}

                        </div>

                        <div class="score">

                            ${Number(
                                my.total || 0
                            ).toFixed(2)}

                        </div>

                    </div>

                    <div class="vs">
                        VS
                    </div>

                    <div>

                        <div class="team-abbrev">

                            ${escapeHtml(
                                opponent.abbrev
                            )}

                        </div>

                        <div class="score">

                            ${Number(
                                opponent.total || 0
                            ).toFixed(2)}

                        </div>

                    </div>

                </div>

            </div>

            <div class="rosters">

                ${renderTeam(
                    my
                )}

                ${renderTeam(
                    opponent
                )}

            </div>

        </div>

    `;
}


function renderTeam(
    team
) {

    const visiblePlayers =
        (team.players || [])
            .filter(
                player =>
                    playerBelongsToSelectedSlate(
                        player
                    )
            );

    return `

        <div class="team-card">

            <div class="team-header">

                <div class="team-name">

                    ${escapeHtml(
                        team.abbrev
                    )}

                </div>

                <div class="team-total">

                    ${Number(
                        team.total || 0
                    ).toFixed(2)}

                </div>

            </div>

            ${

                visiblePlayers.length > 0

                ?

                visiblePlayers
                    .map(
                        renderPlayer
                    )
                    .join("")

                :

                `

                    <div class="no-players">

                        No starters in
                        selected slate

                    </div>

                `
            }

        </div>

    `;
}


function renderPlayer(
    player
) {

    const points =
        player.points === null
        ||
        player.points === undefined
        ?

        "--"

        :

        Number(
            player.points
        ).toFixed(2);

    const statusClass =
        player.status === "LOCKED"
        ?
        "locked"
        :
        "projected";

    const statusText =
        player.status === "LOCKED"
        ?
        "✓ LOCKED"
        :
        "PROJECTED";

    let injuryHtml = "";

    if (
        player.injury
        &&
        player.injury.toUpperCase()
            !== "ACTIVE"
    ) {

        const injuryClass =
            (
                player.injury.toUpperCase()
                === "OUT"
                ||
                player.injury.toUpperCase()
                === "DOUBTFUL"
            )
            ?
            "injury-alert"
            :
            "";

        injuryHtml = `

            <span
                class="
                    injury
                    ${injuryClass}
                "
            >

                ${escapeHtml(
                    player.injury
                )}

            </span>

        `;
    }

    let gameHtml = "";

    if (
        player.nfl_team
        &&
        player.opponent
        &&
        player.game_time
    ) {

        gameHtml = `

            <span class="game-info">

                ${escapeHtml(
                    player.nfl_team
                )}

                vs

                ${escapeHtml(
                    player.opponent
                )}

                ·

                ${escapeHtml(
                    player.game_time
                )}

            </span>

        `;

    } else if (
        player.nfl_team
    ) {

        gameHtml = `

            <span class="game-info">

                ${escapeHtml(
                    player.nfl_team
                )}

            </span>

        `;
    }

    return `

        <div class="player">

            <div class="position">

                ${escapeHtml(
                    player.slot
                )}

            </div>

            <div>

                <div class="player-name">

                    ${escapeHtml(
                        player.name
                    )}

                </div>

                <div class="player-meta">

                    <span
                        class="
                            status
                            ${statusClass}
                        "
                    >

                        ${statusText}

                    </span>

                    ${injuryHtml}

                    ${gameHtml}

                </div>

            </div>

            <div class="points">

                ${points}

                <div class="points-label">
                    PTS
                </div>

            </div>

        </div>

    `;
}


/* ============================================================
   UTILITY
   ============================================================ */

function refreshDashboard() {

    loadDashboard();
}


function escapeHtml(
    value
) {

    if (
        value === null
        ||
        value === undefined
    ) {

        return "";
    }

    return String(value)

        .replace(
            /&/g,
            "&amp;"
        )

        .replace(
            /</g,
            "&lt;"
        )

        .replace(
            />/g,
            "&gt;"
        )

        .replace(
            /"/g,
            "&quot;"
        )

        .replace(
            /'/g,
            "&#039;"
        );
}


loadDashboard();


setInterval(
    loadDashboard,
    60000
);

</script>

</body>

</html>
"""


# ============================================================
# HOME ROUTE
# ============================================================

@app.route("/")
def index():

    return render_template_string(
        HTML
    )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("FANTASY DASHBOARD")
    print("=" * 60)
    print()
    print("Open this in your browser:")
    print()
    print("http://127.0.0.1:5000")
    print()
    print("Press CTRL+C to stop the server.")
    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )