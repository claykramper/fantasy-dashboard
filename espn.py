import requests

from config import (
    ESPN_COOKIES,
    ESPN_FANTASY_URL,
    ESPN_PARAMS,
    ESPN_SEASON,
    MY_OWNER_GUID,
)
from nfl import build_game_lookup


SLOT_NAMES = {
    0: "QB",
    2: "RB",
    4: "WR",
    6: "TE",
    16: "D/ST",
    17: "K",
    23: "FLEX",
}

LINEUP_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "K", "D/ST"]


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
    for team in data.get("teams", []):
        if MY_OWNER_GUID in team.get("owners", []):
            return team
    raise RuntimeError("Could not find your ESPN team.")


def find_matchup(data, my_team):
    current_period = data["scoringPeriodId"]

    for game in data.get("schedule", []):
        if game.get("matchupPeriodId") != current_period:
            continue

        home = game.get("home", {})
        away = game.get("away", {})

        if home.get("teamId") == my_team["id"]:
            opponent_id = away.get("teamId")
        elif away.get("teamId") == my_team["id"]:
            opponent_id = home.get("teamId")
        else:
            continue

        for team in data.get("teams", []):
            if team["id"] == opponent_id:
                return team

    raise RuntimeError("Could not find current matchup.")


def get_players(team):
    players = []

    for entry in team.get("roster", {}).get("entries", []):
        slot_id = entry.get("lineupSlotId")
        player = entry.get("playerPoolEntry", {}).get("player", {})

        players.append(
            {
                "player_id": entry.get("playerId"),
                "name": player.get("fullName"),
                "slot": SLOT_NAMES.get(slot_id, "BENCH"),
                "starter": slot_id in SLOT_NAMES,
                "injury_status": player.get("injuryStatus"),
                "pro_team_id": (
                    str(player.get("proTeamId"))
                    if player.get("proTeamId") is not None
                    else None
                ),
            }
        )

    return players


def get_starters(players):
    grouped = {}

    for player in players:
        if player["starter"]:
            grouped.setdefault(player["slot"], []).append(player)

    ordered = []
    for slot in LINEUP_ORDER:
        ordered.extend(grouped.get(slot, []))

    return ordered


def find_player_objects(data, player_id):
    found = []

    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("id") == player_id:
                found.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(data)
    return found


def get_player_stats(data, player_id):
    current_period = data["scoringPeriodId"]
    projections = []
    actuals = []

    for player in find_player_objects(data, player_id):
        for record in player.get("stats", []):
            if not isinstance(record, dict):
                continue
            if record.get("seasonId") != int(ESPN_SEASON):
                continue
            if record.get("scoringPeriodId") != current_period:
                continue

            if (
                record.get("statSourceId") == 1
                and record.get("statSplitTypeId") == 1
                and record.get("appliedTotal") is not None
            ):
                projections.append(float(record["appliedTotal"]))

            if (
                record.get("statSourceId") == 0
                and record.get("statSplitTypeId") == 1
                and record.get("appliedTotal") is not None
            ):
                actuals.append(float(record["appliedTotal"]))

    return (
        projections[0] if projections else None,
        actuals[0] if actuals else None,
    )


def game_finished(game):
    status = str(game.get("game_status") or "").upper()
    detail = str(game.get("status_detail") or "").upper()

    return (
        "FINAL" in status
        or "COMPLETED" in status
        or "FINAL" in detail
        or "END" in detail
    )


def build_espn_matchup(nfl_games):
    data = get_league_data()
    my_team = find_my_team(data)
    opponent = find_matchup(data, my_team)
    game_lookup = build_game_lookup(nfl_games)

    def build_team(team):
        output_players = []
        actual_total = 0.0
        projected_total = 0.0

        for player in get_starters(get_players(team)):
            projected, actual = get_player_stats(
                data,
                player["player_id"],
            )

            game = game_lookup.get(
                str(player.get("pro_team_id")),
                {},
            )

            finished = game_finished(game)

            if actual is not None:
                actual_total += actual

            # The projected matchup score is the expected final score:
            # completed games contribute actual points; live/upcoming
            # games contribute ESPN's current projection.
            if finished and actual is not None:
                projected_total += actual
            elif projected is not None:
                projected_total += projected

            output_players.append(
                {
                    "name": player["name"],
                    "slot": player["slot"],
                    "points": (
                        actual
                        if actual is not None
                        else projected
                    ),
                    "projected": projected,
                    "actual": actual,
                    "status": (
                        "LOCKED"
                        if finished
                        else "PROJECTED"
                    ),
                    "injury": player["injury_status"] or "",
                    "pro_team_id": player["pro_team_id"],
                    "nfl_team": game.get("team", ""),
                    "opponent": game.get("opponent", ""),
                    "game_time": game.get("game_time", ""),
                    "game_status": game.get("game_status", ""),
                    "status_detail": game.get("status_detail", ""),
                }
            )

        return {
            "id": team["id"],
            "name": team["name"],
            "abbrev": team["abbrev"],
            "league": "ESPN",
            "players": output_players,
            "total": actual_total,
            "actual_total": round(actual_total, 2),
            "projected_total": round(projected_total, 2),
        }

    my_data = build_team(my_team)
    opponent_data = build_team(opponent)

    return {
        "platform": "ESPN",
        "week": data["scoringPeriodId"],
        "my_team": my_data,
        "opponent": opponent_data,
        "difference": (
            my_data["actual_total"]
            - opponent_data["actual_total"]
        ),
    }
