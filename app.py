import os
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import requests

from flask import Flask, jsonify, render_template_string
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

ESPN_SWID = os.getenv("ESPN_SWID")
ESPN_S2 = os.getenv("ESPN_S2")
LEAGUE_ID = os.getenv("ESPN_LEAGUE_ID")
SEASON = os.getenv("ESPN_SEASON")

# Your ESPN account owner GUID.
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

# Display NFL times in Central Time.
LOCAL_TIMEZONE = ZoneInfo("America/Chicago")

app = Flask(__name__)


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


# ============================================================
# NFL SCHEDULE
# ============================================================

def get_nfl_schedule():

    """
    Get NFL games for today and the next several days.

    ESPN's public NFL scoreboard endpoint does not require
    fantasy-league authentication.
    """

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
                "dates": date_string
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
                    "id": str(
                        team.get("id")
                    ),
                    "abbreviation": team.get(
                        "abbreviation"
                    ),
                    "display_name": team.get(
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
                "id": event.get("id"),
                "kickoff": kickoff,
                "home": home,
                "away": away,
                "status": type_data.get(
                    "name"
                ),
                "status_detail": type_data.get(
                    "detail"
                ),
            })

    return games


# ============================================================
# NFL SLATES
# ============================================================

def group_games_into_slates(games):

    """
    Group games that begin within 45 minutes of one another.
    """

    if not games:
        return []

    games = sorted(
        games,
        key=lambda game: game["kickoff"]
    )

    slates = []

    for game in games:

        if not slates:

            slates.append({
                "kickoff": game["kickoff"],
                "games": [game],
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
                "kickoff": game["kickoff"],
                "games": [game],
            })

    return slates


def format_slate_label(
    kickoff
):

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


def format_game_time(
    kickoff
):

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


def build_slate_data(
    games
):

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

        is_upcoming = (
            kickoff > now
        )

        output.append({
            "id": index,
            "label": format_slate_label(
                kickoff
            ),
            "date": local_kickoff.date().isoformat(),
            "kickoff": local_kickoff.isoformat(),
            "timestamp": kickoff.timestamp(),
            "is_upcoming": is_upcoming,
            "games": [
                {
                    "id": game["id"],
                    "away": game["away"][
                        "abbreviation"
                    ],
                    "home": game["home"][
                        "abbreviation"
                    ],
                    "away_id": game["away"]["id"],
                    "home_id": game["home"]["id"],
                    "kickoff": (
                        game["kickoff"]
                        .astimezone(
                            LOCAL_TIMEZONE
                        )
                        .isoformat()
                    ),
                    "game_time": format_game_time(
                        game["kickoff"]
                    ),
                }
                for game in slate["games"]
            ],
        })

    return output


def get_next_slate_index(
    slates
):

    now = datetime.now(
        timezone.utc
    )

    for slate in slates:

        kickoff = datetime.fromtimestamp(
            slate["timestamp"],
            tz=timezone.utc
        )

        if kickoff > now:

            return slate["id"]

    return None


# ============================================================
# TEAM / MATCHUP
# ============================================================

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


def find_matchup(
    data,
    my_team
):

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
# LINEUP
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
            "player_id": entry.get(
                "playerId"
            ),
            "name": player.get(
                "fullName"
            ),
            "slot_id": slot_id,
            "slot": SLOT_NAMES.get(
                slot_id,
                "BENCH"
            ),
            "starter": (
                slot_id in SLOT_NAMES
            ),
            "injury_status": player.get(
                "injuryStatus"
            ),
            "pro_team_id": str(
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
# PLAYER STATS
# ============================================================

def find_player_objects(
    data,
    player_id
):

    found = []

    def search(obj):

        if isinstance(
            obj,
            dict
        ):

            if obj.get("id") == player_id:

                found.append(obj)

            for value in obj.values():

                search(value)

        elif isinstance(
            obj,
            list
        ):

            for value in obj:

                search(value)

    search(data)

    return found


def get_player_stats(
    data,
    player_id
):

    current_period = data[
        "scoringPeriodId"
    ]

    projections = []
    actuals = []

    player_objects = find_player_objects(
        data,
        player_id
    )

    for player in player_objects:

        stats = player.get(
            "stats",
            []
        )

        if not isinstance(
            stats,
            list
        ):

            continue

        for record in stats:

            if not isinstance(
                record,
                dict
            ):

                continue

            if (
                record.get(
                    "seasonId"
                )
                != int(SEASON)
            ):

                continue

            if (
                record.get(
                    "scoringPeriodId"
                )
                != current_period
            ):

                continue

            if (
                record.get(
                    "statSourceId"
                ) == 1
                and record.get(
                    "statSplitTypeId"
                ) == 1
            ):

                applied_total = (
                    record.get(
                        "appliedTotal"
                    )
                )

                if applied_total is not None:

                    projections.append(
                        float(
                            applied_total
                        )
                    )

            if (
                record.get(
                    "statSourceId"
                ) == 0
                and record.get(
                    "statSplitTypeId"
                ) == 1
            ):

                applied_total = (
                    record.get(
                        "appliedTotal"
                    )
                )

                if applied_total is not None:

                    actuals.append(
                        float(
                            applied_total
                        )
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


def get_player_score(
    data,
    player
):

    projection, actual = get_player_stats(
        data,
        player["player_id"]
    )

    if actual is not None:

        return {
            "points": actual,
            "projected": projection,
            "actual": actual,
            "status": "LOCKED",
        }

    return {
        "points": projection,
        "projected": projection,
        "actual": None,
        "status": "PROJECTED",
    }


# ============================================================
# PLAYER GAME INFORMATION
# ============================================================

def build_game_lookup(
    nfl_games
):

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
            "team": game["home"][
                "abbreviation"
            ],
            "opponent": game["away"][
                "abbreviation"
            ],
            "opponent_id": away_id,
            "home": True,
            "kickoff": local_kickoff,
            "game_time": format_game_time(
                game["kickoff"]
            ),
            "game_status": game[
                "status"
            ],
            "status_detail": game[
                "status_detail"
            ],
        }

        lookup[away_id] = {
            "team": game["away"][
                "abbreviation"
            ],
            "opponent": game["home"][
                "abbreviation"
            ],
            "opponent_id": home_id,
            "home": False,
            "kickoff": local_kickoff,
            "game_time": format_game_time(
                game["kickoff"]
            ),
            "game_status": game[
                "status"
            ],
            "status_detail": game[
                "status_detail"
            ],
        }

    return lookup


def get_player_game_info(
    player,
    game_lookup
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
        "team": game["team"],
        "opponent": game["opponent"],
        "game_time": game["game_time"],
        "game_status": game["game_status"],
    }


# ============================================================
# BUILD TEAM DATA
# ============================================================

def build_team_data(
    team,
    players,
    data,
    game_lookup
):

    starters = get_starters(
        players
    )

    output_players = []

    total = 0.0

    for player in starters:

        score = get_player_score(
            data,
            player
        )

        points = score["points"]

        if points is not None:

            total += points

        injury = player[
            "injury_status"
        ]

        if injury is None:
            injury = ""

        game_info = get_player_game_info(
            player,
            game_lookup
        )

        output_players.append({
            "name": player["name"],
            "slot": player["slot"],
            "points": points,
            "projected": score[
                "projected"
            ],
            "actual": score[
                "actual"
            ],
            "status": score[
                "status"
            ],
            "injury": injury,
            "pro_team_id": player[
                "pro_team_id"
            ],
            "nfl_team": game_info[
                "team"
            ],
            "opponent": game_info[
                "opponent"
            ],
            "game_time": game_info[
                "game_time"
            ],
            "game_status": game_info[
                "game_status"
            ],
        })

    return {
        "id": team["id"],
        "name": team["name"],
        "abbrev": team["abbrev"],
        "league": "ESPN",
        "theme": "espn",
        "players": output_players,
        "total": total,
    }


# ============================================================
# COMPLETE DASHBOARD
# ============================================================

def build_dashboard():

    fantasy_data = get_league_data()

    current_period = fantasy_data[
        "scoringPeriodId"
    ]

    my_team = find_my_team(
        fantasy_data
    )

    opponent = find_matchup(
        fantasy_data,
        my_team
    )

    my_players = get_players(
        my_team
    )

    opponent_players = get_players(
        opponent
    )

    nfl_games = get_nfl_schedule()

    game_lookup = build_game_lookup(
        nfl_games
    )

    my_data = build_team_data(
        my_team,
        my_players,
        fantasy_data,
        game_lookup
    )

    opponent_data = build_team_data(
        opponent,
        opponent_players,
        fantasy_data,
        game_lookup
    )

    difference = (
        my_data["total"]
        - opponent_data["total"]
    )

    slates = build_slate_data(
        nfl_games
    )

    next_slate_id = get_next_slate_index(
        slates
    )

    return {
        "week": current_period,
        "updated": time.strftime(
            "%I:%M:%S %p"
        ),
        "my_team": my_data,
        "opponent": opponent_data,
        "difference": difference,
        "slates": slates,
        "next_slate_id": next_slate_id,
    }


# ============================================================
# API
# ============================================================

@app.route("/api/dashboard")
def api_dashboard():

    try:

        return jsonify(
            build_dashboard()
        )

    except Exception as error:

        return jsonify({
            "error": str(error)
        }), 500


# ============================================================
# WEBPAGE
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

<title>Fantasy Dashboard</title>

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
   SCORE
   ============================================================ */

.score-card {

    background: #1d1d1d;

    border-radius: 18px;

    padding: 18px;

    margin-bottom: 14px;

    box-shadow:
        0 2px 10px rgba(0,0,0,.25);
}

.matchup {

    display: grid;

    grid-template-columns: 1fr auto 1fr;

    align-items: center;

    text-align: center;

    gap: 10px;
}

.team-abbrev {

    font-size: 18px;

    font-weight: 800;
}

.score {

    font-size: 36px;

    font-weight: 800;

    line-height: 1;

    margin-top: 6px;
}

.vs {

    color: #777;

    font-size: 13px;

    font-weight: 700;
}

.lead {

    text-align: center;

    margin-top: 14px;

    font-size: 14px;

    font-weight: 600;

    color: #aaa;
}


/* ============================================================
   SLATE SELECTOR
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

    transition:
        background .15s,
        border-color .15s;
}

.slate-option input:checked + label {

    background: #3a3a3a;

    border-color: #777;
}

.slate-option label:active {

    transform: scale(.98);
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

.refresh:active {

    transform: scale(.97);
}


/* ============================================================
   ROSTERS
   ============================================================ */

.rosters {

    display: grid;

    grid-template-columns: 1fr 1fr;

    gap: 14px;
}

.team-card {

    background: #1d1d1d;

    border-radius: 18px;

    overflow: hidden;

    margin-bottom: 14px;

    border-top: 3px solid #3fa66b;
}

.team-header {

    padding: 16px;

    display: flex;

    justify-content: space-between;

    align-items: center;

    border-bottom: 1px solid #303030;

    background:
        linear-gradient(
            90deg,
            rgba(63,166,107,.12),
            transparent
        );
}

.team-name {

    font-weight: 800;

    font-size: 18px;
}

.team-total {

    font-size: 20px;

    font-weight: 800;

    color: #65c98c;
}


/* ============================================================
   PLAYER
   ============================================================ */

.player {

    display: grid;

    grid-template-columns: 42px 1fr auto;

    align-items: center;

    gap: 8px;

    padding: 13px 16px;

    border-bottom: 1px solid #292929;
}

.player:last-child {

    border-bottom: 0;
}

.position {

    color: #888;

    font-size: 12px;

    font-weight: 800;
}

.player-name {

    font-size: 15px;

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

    font-size: 10px;

    font-weight: 800;

    letter-spacing: .5px;
}

.locked {

    color: #7fdc9a;
}

.projected {

    color: #888;
}

.injury {

    font-size: 10px;

    font-weight: 800;

    color: #e6b35a;
}

.injury-alert {

    color: #e86c6c;
}

.points {

    text-align: right;

    font-size: 16px;

    font-weight: 800;
}

.points-label {

    color: #777;

    font-size: 9px;

    font-weight: 600;
}

.no-players {

    padding: 22px;

    text-align: center;

    color: #777;

    font-size: 13px;
}

.loading {

    text-align: center;

    padding: 40px;

    color: #777;
}

.error {

    background: #351c1c;

    color: #ff9d9d;

    padding: 15px;

    border-radius: 12px;

    font-size: 13px;

    white-space: pre-wrap;
}


/* ============================================================
   PHONE
   ============================================================ */

@media (max-width: 700px) {

    .container {

        padding: 10px;
    }

    .rosters {

        grid-template-columns: 1fr;

        gap: 0;
    }

    .score {

        font-size: 31px;
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

    .player {

        padding: 13px 14px;
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

        <div
            class="subtitle"
            id="week"
        >
            Loading...
        </div>

    </div>


    <div
        id="content"
        class="loading"
    >
        Loading ESPN...
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
                "Unknown ESPN error"
            );
        }

        dashboardData = data;

        initializeSelectedSlates();

        renderDashboard();

    } catch (error) {

        content.innerHTML = `
            <div class="error">
                ${escapeHtml(error.message)}
            </div>
        `;
    }
}


function initializeSelectedSlates() {

    if (
        selectedSlates.size === 0 &&
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
        selectedSlates.has(
            slateId
        )
    ) {

        selectedSlates.delete(
            slateId
        );

    } else {

        selectedSlates.add(
            slateId
        );
    }

    renderDashboard();
}


function renderDashboard() {

    const content =
        document.getElementById("content");

    const my =
        dashboardData.my_team;

    const opponent =
        dashboardData.opponent;

    const difference =
        dashboardData.difference;

    document.getElementById("week")
        .textContent =
        `Week ${dashboardData.week}`;


    let leadText;

    if (difference > 0) {

        leadText =
            `${my.abbrev} leads by ${difference.toFixed(2)}`;

    } else if (difference < 0) {

        leadText =
            `${opponent.abbrev} leads by ${Math.abs(difference).toFixed(2)}`;

    } else {

        leadText = "Tied";
    }


    content.innerHTML = `

        <div class="score-card">

            <div class="matchup">

                <div>

                    <div class="team-abbrev">
                        ${escapeHtml(my.abbrev)}
                    </div>

                    <div class="score">
                        ${my.total.toFixed(2)}
                    </div>

                </div>


                <div class="vs">
                    VS
                </div>


                <div>

                    <div class="team-abbrev">
                        ${escapeHtml(opponent.abbrev)}
                    </div>

                    <div class="score">
                        ${opponent.total.toFixed(2)}
                    </div>

                </div>

            </div>


            <div class="lead">
                ${escapeHtml(leadText)}
            </div>

        </div>


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


        <div class="rosters">

            ${renderTeam(my)}

            ${renderTeam(opponent)}

        </div>

    `;
}


function renderSlateSelector() {

    if (
        !dashboardData.slates ||
        dashboardData.slates.length === 0
    ) {

        return "";
    }


    const options =
        dashboardData.slates
            .map(
                slate => {

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
                }
            )
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


function playerBelongsToSelectedSlate(
    player
) {

    if (
        selectedSlates.size === 0
    ) {

        return false;
    }

    if (
        !player.pro_team_id
    ) {

        return false;
    }

    const playerTeam =
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

            if (
                String(
                    game.home_id
                ) === playerTeam
                ||
                String(
                    game.away_id
                ) === playerTeam
            ) {

                return true;
            }
        }
    }

    return false;
}


function renderTeam(
    team
) {

    const visiblePlayers =
        team.players.filter(
            player =>
                playerBelongsToSelectedSlate(
                    player
                )
        );


    return `

        <div class="
            team-card
            ${escapeHtml(team.theme)}
        ">

            <div class="team-header">

                <div class="team-name">
                    ${escapeHtml(
                        team.abbrev
                    )}
                </div>

                <div class="team-total">
                    ${team.total.toFixed(2)}
                </div>

            </div>


            ${
                visiblePlayers.length > 0
                    ? visiblePlayers
                        .map(
                            renderPlayer
                        )
                        .join("")
                    : `
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
            ? "--"
            : player.points.toFixed(2);

    const statusClass =
        player.status === "LOCKED"
            ? "locked"
            : "projected";

    const statusText =
        player.status === "LOCKED"
            ? "✓ LOCKED"
            : "PROJECTED";


    let injuryHtml = "";

    if (
        player.injury &&
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
                ? "injury-alert"
                : "";

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
        player.nfl_team &&
        player.opponent &&
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


function refreshDashboard() {

    loadDashboard();
}


function escapeHtml(
    value
) {

    if (
        value === null ||
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


// Automatically refresh every minute.
setInterval(
    loadDashboard,
    60000
);

</script>

</body>

</html>
"""


# ============================================================
# HOME PAGE
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
        debug=False
    )