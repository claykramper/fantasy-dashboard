import time

import requests

from config import (
    SLEEPER_API_URL,
    SLEEPER_PROJECTIONS_URL,
    SLEEPER_STATS_URL,
    SLEEPER_USERNAME,
)

PLAYER_CACHE = None
PLAYER_CACHE_TIME = 0

PROJECTION_CACHE = {}
STATS_CACHE = {}


# ============================================================
# BASIC SLEEPER API
# ============================================================

def sleeper_get(path):
    response = requests.get(
        f"{SLEEPER_API_URL}{path}",
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_sleeper_user():
    return sleeper_get(f"/user/{SLEEPER_USERNAME}")


def get_sleeper_leagues(user_id):
    return sleeper_get(
        f"/user/{user_id}/leagues/nfl/2026"
    )


def get_sleeper_state():
    return sleeper_get("/state/nfl")


def get_sleeper_league(league_id):
    return sleeper_get(
        f"/league/{league_id}"
    )


def get_sleeper_rosters(league_id):
    return sleeper_get(
        f"/league/{league_id}/rosters"
    )


def get_sleeper_users(league_id):
    return sleeper_get(
        f"/league/{league_id}/users"
    )


def get_sleeper_matchups(league_id, week):
    return sleeper_get(
        f"/league/{league_id}/matchups/{week}"
    )


# ============================================================
# PLAYER DATABASE
# ============================================================

def get_sleeper_players():
    global PLAYER_CACHE
    global PLAYER_CACHE_TIME

    if (
        PLAYER_CACHE is not None
        and time.time() - PLAYER_CACHE_TIME < 86400
    ):
        return PLAYER_CACHE

    PLAYER_CACHE = sleeper_get("/players/nfl")
    PLAYER_CACHE_TIME = time.time()

    return PLAYER_CACHE


# ============================================================
# PROJECTIONS / ACTUAL STATS
# ============================================================

def get_projection_data(season, week):
    cache_key = (int(season), int(week))

    cached = PROJECTION_CACHE.get(cache_key)

    if cached is not None:
        cached_time, cached_data = cached

        if time.time() - cached_time < 300:
            return cached_data

    response = requests.get(
        f"{SLEEPER_PROJECTIONS_URL}/{season}/{week}",
        params={
            "season_type": "regular",
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    PROJECTION_CACHE[cache_key] = (
        time.time(),
        data,
    )

    return data


def get_stats_data(season, week):
    cache_key = (int(season), int(week))

    cached = STATS_CACHE.get(cache_key)

    if cached is not None:
        cached_time, cached_data = cached

        if time.time() - cached_time < 60:
            return cached_data

    response = requests.get(
        f"{SLEEPER_STATS_URL}/regular/{season}/{week}",
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    STATS_CACHE[cache_key] = (
        time.time(),
        data,
    )

    return data


# ============================================================
# GENERAL HELPERS
# ============================================================

def choose_league(leagues):
    if not leagues:
        raise RuntimeError(
            "No Sleeper NFL leagues found."
        )

    for league in leagues:
        if league.get("status") == "in_season":
            return league

    return leagues[0]


def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def player_position(player):
    positions = player.get("fantasy_positions") or []

    if positions:
        return positions[0]

    return player.get("position", "")


def rows_by_player(data):
    """
    Sleeper projections currently come back as a list:

        [
            {
                "player_id": "10881",
                "stats": {...},
                ...
            }
        ]

    Stats responses can also be dictionaries keyed by player ID.
    Normalize both formats into:

        {
            "player_id": row
        }
    """

    if isinstance(data, dict):
        return {
            str(player_id): row
            for player_id, row in data.items()
        }

    if isinstance(data, list):
        result = {}

        for row in data:
            if not isinstance(row, dict):
                continue

            player_id = row.get("player_id")

            if player_id is None:
                continue

            result[str(player_id)] = row

        return result

    return {}


# ============================================================
# CUSTOM SCORING
# ============================================================

def score_offensive_player(stats):
    """
    Your league is standard half-PPR offensive scoring:

        pass_yd   = 0.04
        pass_td   = 4
        pass_int  = -1
        pass_2pt  = 2

        rush_yd   = 0.10
        rush_td   = 6
        rush_2pt  = 2

        rec       = 0.50
        rec_yd    = 0.10
        rec_td    = 6
        rec_2pt   = 2

        fum_lost  = -2
    """

    total = 0.0

    total += number(stats.get("pass_yd")) * 0.04
    total += number(stats.get("pass_td")) * 4.0
    total += number(stats.get("pass_int")) * -1.0
    total += number(stats.get("pass_2pt")) * 2.0

    total += number(stats.get("rush_yd")) * 0.10
    total += number(stats.get("rush_td")) * 6.0
    total += number(stats.get("rush_2pt")) * 2.0

    total += number(stats.get("rec")) * 0.50
    total += number(stats.get("rec_yd")) * 0.10
    total += number(stats.get("rec_td")) * 6.0
    total += number(stats.get("rec_2pt")) * 2.0

    total += number(stats.get("fum_lost")) * -2.0

    return round(total, 2)


def score_kicker(stats):
    """
    Your league's kicker scoring:

        FG 0-19   = 3
        FG 20-29  = 3
        FG 30-39  = 3
        FG 40-49  = 4
        FG 50-59  = 5
        FG 60+    = 6

        XP made   = 1
        FG miss   = -1
        XP miss   = -1
    """

    total = 0.0

    total += number(stats.get("fgm_0_19")) * 3.0
    total += number(stats.get("fgm_20_29")) * 3.0
    total += number(stats.get("fgm_30_39")) * 3.0
    total += number(stats.get("fgm_40_49")) * 4.0
    total += number(stats.get("fgm_50_59")) * 5.0
    total += number(stats.get("fgm_60p")) * 6.0

    total += number(stats.get("xpm")) * 1.0
    total += number(stats.get("fgmiss")) * -1.0
    total += number(stats.get("xpmiss")) * -1.0

    return round(total, 2)


def get_points_allowed(stats):
    """
    Return the projected/actual points allowed value using
    whichever Sleeper field is present.
    """

    for key in (
        "pts_allow",
        "pts_allowed",
        "points_allowed",
    ):
        if key in stats:
            return number(stats.get(key))

    return None


def score_defense(stats):
    """
    Your league's D/ST scoring:

        sack          = 1
        int           = 2
        fum_rec       = 2
        safe          = 2
        blk_kick      = 2
        def_td        = 6
        st_td         = 6
        fum_rec_td    = 6
        def_st_td     = 6
        ff            = 1
        st_ff         = 1
        def_st_fum_rec= 1

    Points allowed:

        0       = 10
        1-6     = 7
        7-13    = 4
        14-20   = 1
        21-27   = 0
        28-34   = -1
        35+     = -4
    """

    total = 0.0

    total += number(stats.get("sack")) * 1.0
    total += number(stats.get("int")) * 2.0
    total += number(stats.get("fum_rec")) * 2.0
    total += number(stats.get("safe")) * 2.0
    total += number(stats.get("blk_kick")) * 2.0

    total += number(stats.get("def_td")) * 6.0
    total += number(stats.get("st_td")) * 6.0
    total += number(stats.get("fum_rec_td")) * 6.0
    total += number(stats.get("def_st_td")) * 6.0

    total += number(stats.get("ff")) * 1.0
    total += number(stats.get("st_ff")) * 1.0
    total += number(stats.get("def_st_ff")) * 1.0
    total += number(stats.get("def_st_fum_rec")) * 1.0

    points_allowed = get_points_allowed(stats)

    if points_allowed is not None:
        if points_allowed == 0:
            total += 10.0

        elif points_allowed <= 6:
            total += 7.0

        elif points_allowed <= 13:
            total += 4.0

        elif points_allowed <= 20:
            total += 1.0

        elif points_allowed <= 27:
            total += 0.0

        elif points_allowed <= 34:
            total -= 1.0

        else:
            total -= 4.0

    return round(total, 2)


def calculate_actual_points(
    stats,
    position,
):
    """
    Calculate actual fantasy points from the raw weekly stat line.
    """

    if not isinstance(stats, dict):
        return None

    pos = str(position or "").upper()

    if pos == "K":
        return score_kicker(stats)

    if pos in {
        "DEF",
        "DST",
        "D/ST",
    }:
        return score_defense(stats)

    return score_offensive_player(stats)


# ============================================================
# PLAYER SCORE
# ============================================================

def get_player_score(
    player_id,
    player,
    projections,
    actuals,
):
    """
    Return:

        projected points
        actual points

    Projections:
        Offensive players use Sleeper's pts_half_ppr because
        your league is 0.5 PPR.

        Kickers / defenses are calculated from the raw
        projection statistics using your league settings.

    Actuals:
        Calculated from the raw weekly stats so they follow
        your league's scoring.
    """

    pid = str(player_id)
    position = player_position(player)
    pos = str(position or "").upper()

    projected_rows = rows_by_player(projections)
    actual_rows = rows_by_player(actuals)

    projected_row = projected_rows.get(pid)
    actual_row = actual_rows.get(pid)

    projected = None
    actual = None

    # --------------------------------------------------------
    # PROJECTED
    # --------------------------------------------------------

    if projected_row:
        projection_stats = projected_row.get(
            "stats",
            projected_row,
        )

        if pos not in {"K", "DEF", "DST", "D/ST"}:
            # Your league is half-PPR.
            projected = projection_stats.get(
                "pts_half_ppr"
            )

            # Safety fallback if Sleeper doesn't provide it.
            if projected is None:
                projected = score_offensive_player(
                    projection_stats
                )

        elif pos == "K":
            projected = score_kicker(
                projection_stats
            )

        else:
            projected = score_defense(
                projection_stats
            )

    # --------------------------------------------------------
    # ACTUAL
    # --------------------------------------------------------

    if actual_row:
        actual_stats = actual_row.get(
            "stats",
            actual_row,
        )

        # Some Sleeper stat rows have gp=0 while still
        # containing placeholder fields.
        has_played = (
            number(actual_stats.get("gp")) > 0
            or number(actual_stats.get("g")) > 0
        )

        if has_played:
            actual = calculate_actual_points(
                actual_stats,
                position,
            )

    if projected is not None:
        projected = round(float(projected), 2)

    if actual is not None:
        actual = round(float(actual), 2)

    return projected, actual


# ============================================================
# GAME INFORMATION
# ============================================================

def game_info(
    team_abbreviation,
    game_lookup,
):
    team = str(
        team_abbreviation or ""
    ).upper()

    game = game_lookup.get(team)

    if not game:
        return {
            "team": team_abbreviation or "",
            "opponent": "",
            "game_time": "",
            "game_status": "",
            "status_detail": "",
        }

    return {
        "team": game["team"],
        "opponent": game["opponent"],
        "game_time": game["game_time"],
        "game_status": game["game_status"],
        "status_detail": game.get(
            "status_detail",
            "",
        ),
    }


# ============================================================
# BUILD PLAYER DATA
# ============================================================

def build_players(
    matchup,
    players,
    projections,
    actuals,
    game_lookup,
):
    output = []

    for player_id in matchup.get("starters", []):
        pid = str(player_id)

        player = players.get(pid)

        if not player:
            continue

        position = player_position(player)

        projected, actual = get_player_score(
            pid,
            player,
            projections,
            actuals,
        )

        team = player.get("team") or ""

        game = game_info(
            team,
            game_lookup,
        )

        status_name = str(
            game.get("game_status") or ""
        ).upper()

        finished = (
            "FINAL" in status_name
            or "COMPLETED" in status_name
        )

        live = (
            "IN_PROGRESS" in status_name
            or "LIVE" in status_name
        )

        if finished:
            display_status = "LOCKED"
        elif live:
            display_status = "LIVE"
        else:
            display_status = "PROJECTED"

        name = (
            player.get("full_name")
            or " ".join(
                part
                for part in (
                    player.get("first_name", ""),
                    player.get("last_name", ""),
                )
                if part
            )
        )

        # Current points shown to the user.
        if actual is not None:
            current_points = actual
        elif projected is not None:
            current_points = projected
        else:
            current_points = None

        output.append(
            {
                "name": name,
                "slot": position or "FLEX",
                "player_id": pid,
                "nfl_team": game["team"],
                "opponent": game["opponent"],
                "game_time": game["game_time"],
                "game_status": game["game_status"],
                "status_detail": game.get(
                    "status_detail",
                    "",
                ),
                "points": current_points,
                "projected": projected,
                "actual": actual,
                "injury": player.get(
                    "injury_status"
                ) or "",
                "status": display_status,
                "pro_team_id": team,
            }
        )

    return output


# ============================================================
# TEAM NAMES
# ============================================================

def team_name(
    roster,
    users,
):
    metadata = roster.get(
        "metadata"
    ) or {}

    if metadata.get("team_name"):
        return metadata["team_name"]

    owner_id = roster.get(
        "owner_id"
    )

    for user in users:
        if user.get("user_id") == owner_id:
            return (
                user.get("display_name")
                or user.get("username")
                or f"Roster {roster.get('roster_id')}"
            )

    return f"Roster {roster.get('roster_id')}"


# ============================================================
# TEAM TOTALS
# ============================================================

def calculate_actual_total(players):
    total = 0.0

    for player in players:
        if player.get("actual") is not None:
            total += number(
                player["actual"]
            )

    return round(total, 2)


def calculate_projected_total(players):
    """
    IMPORTANT:

    Projection is always the expected final score for every
    starter. We do NOT replace projections with actual points.

    Example:

        Player A actual = 18
        Player B projection = 15
        Player C projection = 12

    Projected team total = 45

    This is what the user expects to see.
    """

    total = 0.0

    for player in players:
        if player.get("projected") is not None:
            total += number(
                player["projected"]
            )

    return round(total, 2)


# ============================================================
# MAIN MATCHUP BUILDER
# ============================================================

def build_sleeper_matchup(game_lookup):
    user = get_sleeper_user()

    if not user:
        raise RuntimeError(
            "Sleeper user not found."
        )

    leagues = get_sleeper_leagues(
        user["user_id"]
    )

    league = choose_league(
        leagues
    )

    league_id = league["league_id"]

    league_data = get_sleeper_league(
        league_id
    )

    state = get_sleeper_state()

    week = int(
        state.get("week") or 1
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

    # --------------------------------------------------------
    # OUR ROSTER
    # --------------------------------------------------------

    my_roster = next(
        (
            roster
            for roster in rosters
            if roster.get("owner_id")
            == user["user_id"]
        ),
        None,
    )

    if not my_roster:
        raise RuntimeError(
            "Could not find your Sleeper roster."
        )

    # --------------------------------------------------------
    # OUR MATCHUP
    # --------------------------------------------------------

    my_matchup = next(
        (
            matchup
            for matchup in matchups
            if matchup.get("roster_id")
            == my_roster["roster_id"]
        ),
        None,
    )

    if not my_matchup:
        raise RuntimeError(
            "Could not find your Sleeper matchup."
        )

    matchup_id = my_matchup.get(
        "matchup_id"
    )

    # --------------------------------------------------------
    # OPPONENT MATCHUP
    # --------------------------------------------------------

    opponent_matchup = next(
        (
            matchup
            for matchup in matchups
            if (
                matchup.get("matchup_id")
                == matchup_id
                and
                matchup.get("roster_id")
                != my_roster["roster_id"]
            )
        ),
        None,
    )

    if not opponent_matchup:
        raise RuntimeError(
            "Could not find your Sleeper opponent."
        )

    # --------------------------------------------------------
    # OPPONENT ROSTER
    # --------------------------------------------------------

    opponent_roster = next(
        (
            roster
            for roster in rosters
            if roster.get("roster_id")
            == opponent_matchup.get(
                "roster_id"
            )
        ),
        None,
    )

    if not opponent_roster:
        raise RuntimeError(
            "Could not find your Sleeper opponent roster."
        )

    # --------------------------------------------------------
    # PLAYER / PROJECTION / STATS DATA
    # --------------------------------------------------------

    players = get_sleeper_players()

    projections = get_projection_data(
        2026,
        week,
    )

    actuals = get_stats_data(
        2026,
        week,
    )

    # --------------------------------------------------------
    # PLAYER DATA
    # --------------------------------------------------------

    my_players = build_players(
        my_matchup,
        players,
        projections,
        actuals,
        game_lookup,
    )

    opponent_players = build_players(
        opponent_matchup,
        players,
        projections,
        actuals,
        game_lookup,
    )

    # --------------------------------------------------------
    # TEAM TOTALS
    # --------------------------------------------------------

    my_actual = calculate_actual_total(
        my_players
    )

    opponent_actual = calculate_actual_total(
        opponent_players
    )

    my_projected = calculate_projected_total(
        my_players
    )

    opponent_projected = calculate_projected_total(
        opponent_players
    )

    # Sleeper's matchup points are retained as the platform's
    # official current matchup total. Our player-calculated
    # actual total is separately available for comparison.
    my_matchup_points = number(
        my_matchup.get("points")
    )

    opponent_matchup_points = number(
        opponent_matchup.get("points")
    )

    # --------------------------------------------------------
    # RETURN DASHBOARD DATA
    # --------------------------------------------------------

    return {
        "platform": "Sleeper",
        "week": week,
        "league_name": (
            league_data.get("name")
            or league.get("name")
        ),

        "my_team": {
            "id": my_roster["roster_id"],
            "name": team_name(
                my_roster,
                users,
            ),
            "abbrev": team_name(
                my_roster,
                users,
            ),
            "league": "Sleeper",
            "players": my_players,

            # Official Sleeper matchup total
            "total": my_matchup_points,

            # Player-calculated actual score
            "actual_total": my_actual,

            # Expected final score
            "projected_total": my_projected,
        },

        "opponent": {
            "id": opponent_roster["roster_id"],
            "name": team_name(
                opponent_roster,
                users,
            ),
            "abbrev": team_name(
                opponent_roster,
                users,
            ),
            "league": "Sleeper",
            "players": opponent_players,

            "total": opponent_matchup_points,
            "actual_total": opponent_actual,
            "projected_total": opponent_projected,
        },

        "difference": round(
            my_matchup_points
            - opponent_matchup_points,
            2,
        ),
    }