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

PLAYER_CACHE_SECONDS = 86400
PROJECTION_CACHE_SECONDS = 45
STATS_CACHE_SECONDS = 20


def sleeper_get(path):
    response = requests.get(f"{SLEEPER_API_URL}{path}", timeout=20)
    response.raise_for_status()
    return response.json()


def get_sleeper_user():
    return sleeper_get(f"/user/{SLEEPER_USERNAME}")


def get_sleeper_leagues(user_id):
    return sleeper_get(f"/user/{user_id}/leagues/nfl/2026")


def get_sleeper_state():
    return sleeper_get("/state/nfl")


def get_sleeper_league(league_id):
    return sleeper_get(f"/league/{league_id}")


def get_sleeper_rosters(league_id):
    return sleeper_get(f"/league/{league_id}/rosters")


def get_sleeper_users(league_id):
    return sleeper_get(f"/league/{league_id}/users")


def get_sleeper_matchups(league_id, week):
    return sleeper_get(f"/league/{league_id}/matchups/{week}")


def get_sleeper_players():
    global PLAYER_CACHE, PLAYER_CACHE_TIME
    if PLAYER_CACHE is not None and time.time() - PLAYER_CACHE_TIME < PLAYER_CACHE_SECONDS:
        return PLAYER_CACHE
    PLAYER_CACHE = sleeper_get("/players/nfl")
    PLAYER_CACHE_TIME = time.time()
    return PLAYER_CACHE


def get_projection_data(season, week, force_refresh=False):
    key = (int(season), int(week))
    cached = PROJECTION_CACHE.get(key)
    if not force_refresh and cached and time.time() - cached[0] < PROJECTION_CACHE_SECONDS:
        return cached[1]

    response = requests.get(
        f"{SLEEPER_PROJECTIONS_URL}/{season}/{week}",
        params={"season_type": "regular"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    PROJECTION_CACHE[key] = (time.time(), data)
    return data


def get_stats_data(season, week, force_refresh=False):
    key = (int(season), int(week))
    cached = STATS_CACHE.get(key)
    if not force_refresh and cached and time.time() - cached[0] < STATS_CACHE_SECONDS:
        return cached[1]

    response = requests.get(
        f"{SLEEPER_STATS_URL}/regular/{season}/{week}",
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    STATS_CACHE[key] = (time.time(), data)
    return data


def choose_league(leagues):
    if not leagues:
        raise RuntimeError("No Sleeper NFL leagues found.")
    for league in leagues:
        if league.get("status") == "in_season":
            return league
    return leagues[0]


def player_position(player):
    positions = player.get("fantasy_positions") or []
    return positions[0] if positions else player.get("position", "")


def rows_by_player(data):
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    if isinstance(data, list):
        return {
            str(row["player_id"]): row
            for row in data
            if isinstance(row, dict) and row.get("player_id") is not None
        }
    return {}


def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def score_offensive_player(stats):
    total = 0.0
    total += number(stats.get("pass_yd")) * 0.04
    total += number(stats.get("pass_td")) * 4
    total += number(stats.get("pass_int")) * -1
    total += number(stats.get("pass_2pt")) * 2
    total += number(stats.get("rush_yd")) * 0.10
    total += number(stats.get("rush_td")) * 6
    total += number(stats.get("rush_2pt")) * 2
    total += number(stats.get("rec")) * 0.50
    total += number(stats.get("rec_yd")) * 0.10
    total += number(stats.get("rec_td")) * 6
    total += number(stats.get("rec_2pt")) * 2
    total += number(stats.get("fum_lost")) * -2
    return round(total, 2)


def score_kicker(stats):
    total = 0.0
    total += number(stats.get("fgm_0_19")) * 3
    total += number(stats.get("fgm_20_29")) * 3
    total += number(stats.get("fgm_30_39")) * 3
    total += number(stats.get("fgm_40_49")) * 4
    total += number(stats.get("fgm_50_59")) * 5
    total += number(stats.get("fgm_60p")) * 6
    total += number(stats.get("xpm")) * 1
    total += number(stats.get("fgmiss")) * -1
    total += number(stats.get("xpmiss")) * -1
    return round(total, 2)


def score_defense(stats):
    total = 0.0
    total += number(stats.get("sack")) * 1
    total += number(stats.get("int")) * 2
    total += number(stats.get("fum_rec")) * 2
    total += number(stats.get("safe")) * 2
    total += number(stats.get("blk_kick")) * 2
    total += number(stats.get("def_td")) * 6
    total += number(stats.get("st_td")) * 6
    total += number(stats.get("def_st_td")) * 6
    total += number(stats.get("fum_rec_td")) * 6
    total += number(stats.get("ff")) * 1
    total += number(stats.get("st_ff")) * 1
    total += number(stats.get("def_st_ff")) * 1
    return round(total, 2)


def calculate_actual_points(stats, position):
    pos = str(position or "").upper()
    if pos == "K":
        return score_kicker(stats)
    if pos in {"DEF", "DST", "D/ST"}:
        return score_defense(stats)
    return score_offensive_player(stats)


def get_player_score(player_id, player, projections, actuals):
    pid = str(player_id)
    position = player_position(player)
    pos = str(position or "").upper()

    projected_rows = rows_by_player(projections)
    actual_rows = rows_by_player(actuals)
    projected_row = projected_rows.get(pid)
    actual_row = actual_rows.get(pid)

    projected = None
    actual = None

    if projected_row:
        stats = projected_row.get("stats", projected_row)
        if pos not in {"K", "DEF", "DST", "D/ST"}:
            projected = stats.get("pts_half_ppr")
            if projected is None:
                projected = score_offensive_player(stats)
        elif pos == "K":
            projected = score_kicker(stats)
        else:
            projected = score_defense(stats)

    if actual_row:
        stats = actual_row.get("stats", actual_row)
        if number(stats.get("gp")) > 0 or number(stats.get("g")) > 0:
            actual = calculate_actual_points(stats, position)

    if projected is not None:
        projected = round(float(projected), 2)
    if actual is not None:
        actual = round(float(actual), 2)

    return projected, actual


def game_info(team_abbreviation, game_lookup):
    team = str(team_abbreviation or "").upper()
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
        "status_detail": game.get("status_detail", ""),
    }


def build_players(matchup, players, projections, actuals, game_lookup):
    output = []
    for player_id in matchup.get("starters", []):
        pid = str(player_id)
        player = players.get(pid)
        if not player:
            continue

        position = player_position(player)
        projected, actual = get_player_score(
            pid, player, projections, actuals
        )
        team = player.get("team") or ""
        game = game_info(team, game_lookup)
        status_name = str(game.get("game_status") or "").upper()
        finished = "FINAL" in status_name or "COMPLETED" in status_name
        live = "IN_PROGRESS" in status_name or "LIVE" in status_name

        display_status = "LOCKED" if finished else "LIVE" if live else "PROJECTED"
        name = player.get("full_name") or " ".join(
            part for part in (player.get("first_name", ""), player.get("last_name", "")) if part
        )

        output.append({
            "name": name,
            "slot": position or "FLEX",
            "player_id": pid,
            "nfl_team": game["team"],
            "opponent": game["opponent"],
            "game_time": game["game_time"],
            "game_status": game["game_status"],
            "status_detail": game.get("status_detail", ""),
            "points": actual if actual is not None else projected,
            "projected": projected,
            "actual": actual,
            "injury": player.get("injury_status") or "",
            "status": display_status,
            "pro_team_id": team,
        })
    return output


def team_name(roster, users):
    metadata = roster.get("metadata") or {}
    if metadata.get("team_name"):
        return metadata["team_name"]
    owner_id = roster.get("owner_id")
    for user in users:
        if user.get("user_id") == owner_id:
            return user.get("display_name") or user.get("username") or f"Roster {roster.get('roster_id')}"
    return f"Roster {roster.get('roster_id')}"


def calculate_actual_total(players):
    return round(sum(number(p.get("actual")) for p in players if p.get("actual") is not None), 2)


def calculate_projected_total(players):
    return round(sum(number(p.get("projected")) for p in players if p.get("projected") is not None), 2)


def build_sleeper_matchup(game_lookup):
    user = get_sleeper_user()
    leagues = get_sleeper_leagues(user["user_id"])
    league = choose_league(leagues)
    league_id = league["league_id"]
    league_data = get_sleeper_league(league_id)
    state = get_sleeper_state()
    week = int(state.get("week") or 1)
    rosters = get_sleeper_rosters(league_id)
    users = get_sleeper_users(league_id)
    matchups = get_sleeper_matchups(league_id, week)

    my_roster = next((r for r in rosters if r.get("owner_id") == user["user_id"]), None)
    if not my_roster:
        raise RuntimeError("Could not find your Sleeper roster.")

    my_matchup = next((m for m in matchups if m.get("roster_id") == my_roster["roster_id"]), None)
    if not my_matchup:
        raise RuntimeError("Could not find your Sleeper matchup.")

    opponent_matchup = next((m for m in matchups if m.get("matchup_id") == my_matchup.get("matchup_id") and m.get("roster_id") != my_roster["roster_id"]), None)
    if not opponent_matchup:
        raise RuntimeError("Could not find your Sleeper opponent.")

    opponent_roster = next((r for r in rosters if r.get("roster_id") == opponent_matchup["roster_id"]), None)
    if not opponent_roster:
        raise RuntimeError("Could not find your Sleeper opponent roster.")

    players = get_sleeper_players()
    projections = get_projection_data(2026, week)
    actuals = get_stats_data(2026, week)

    my_players = build_players(my_matchup, players, projections, actuals, game_lookup)
    opponent_players = build_players(opponent_matchup, players, projections, actuals, game_lookup)

    my_actual = calculate_actual_total(my_players)
    opp_actual = calculate_actual_total(opponent_players)
    my_projected = calculate_projected_total(my_players)
    opp_projected = calculate_projected_total(opponent_players)

    return {
        "platform": "Sleeper",
        "week": week,
        "league_name": league_data.get("name") or league.get("name"),
        "my_team": {
            "id": my_roster["roster_id"],
            "name": team_name(my_roster, users),
            "abbrev": team_name(my_roster, users),
            "league": "Sleeper",
            "players": my_players,
            "total": number(my_matchup.get("points")),
            "actual_total": my_actual,
            "projected_total": my_projected,
        },
        "opponent": {
            "id": opponent_roster["roster_id"],
            "name": team_name(opponent_roster, users),
            "abbrev": team_name(opponent_roster, users),
            "league": "Sleeper",
            "players": opponent_players,
            "total": number(opponent_matchup.get("points")),
            "actual_total": opp_actual,
            "projected_total": opp_projected,
        },
        "difference": number(my_matchup.get("points")) - number(opponent_matchup.get("points")),
    }
