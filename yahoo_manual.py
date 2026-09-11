from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from sleeper import (
    get_projection_data,
    get_sleeper_players,
    get_sleeper_state,
    get_stats_data,
)


YAHOO_ROSTER = [
    {"name": "Bo Nix", "position": "QB", "roster_slot": "QB"},
    {"name": "De'Von Achane", "position": "RB", "roster_slot": "RB"},
    {"name": "Chase Brown", "position": "RB", "roster_slot": "RB"},
    {"name": "Ladd McConkey", "position": "WR", "roster_slot": "WR"},
    {"name": "DJ Moore", "position": "WR", "roster_slot": "WR"},
    {"name": "Travis Etienne Jr.", "position": "RB", "roster_slot": "W/R/T"},
    {"name": "Trey McBride", "position": "TE", "roster_slot": "W/R/T"},
    {"name": "Rhamondre Stevenson", "position": "RB", "roster_slot": "W/R/T"},
    {"name": "Carnell Tate", "position": "WR", "roster_slot": "BN"},
    {"name": "Chuba Hubbard", "position": "RB", "roster_slot": "BN"},
    {"name": "Kyle Pitts Sr.", "position": "TE", "roster_slot": "BN"},
    {"name": "De'Zhaun Stribling", "position": "WR", "roster_slot": "BN"},
    {"name": "Makai Lemon", "position": "WR", "roster_slot": "BN"},
    {"name": "Jordyn Tyson", "position": "WR", "roster_slot": "IR"},
    {"name": "Nick Folk", "position": "K", "roster_slot": "K", "team": "ATL"},
    {"name": "Eagles", "position": "DEF", "roster_slot": "DEF", "team": "PHI"},
]

ROSTER_REQUIREMENTS = {"QB": 1, "RB": 2, "WR": 2, "FLEX": 3, "K": 1, "DEF": 1}
FLEX_POSITIONS = {"RB", "WR", "TE"}
CLOSE_THRESHOLD = 1.5


def num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_name(name):
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[.'\-]", "", text)
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    return "".join(word for word in text.split() if word not in suffixes)


def normalize_team(team):
    return re.sub(r"[^a-z0-9]", "", str(team or "").lower())


def projection_rows_by_player(data):
    if isinstance(data, list):
        return {str(r["player_id"]): r for r in data if isinstance(r, dict) and r.get("player_id") is not None}
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    return {}


def _sleeper_display_name(player):
    return player.get("full_name") or " ".join(
        p for p in (player.get("first_name", ""), player.get("last_name", "")) if p
    )


def _sleeper_positions(player):
    values = {str(player.get("position") or "").upper()}
    values.update(str(x).upper() for x in (player.get("fantasy_positions") or []))
    return values


def find_sleeper_player(manual, sleeper_players):
    target_name = normalize_name(manual["name"])
    target_position = str(manual["position"]).upper()
    target_team = normalize_team(manual.get("team"))

    if target_position == "DEF" and target_team:
        for player_id, player in sleeper_players.items():
            if normalize_team(player.get("team")) != target_team:
                continue
            if _sleeper_positions(player) & {"DEF", "DST", "D/ST"}:
                return player_id, player

    exact = []
    for player_id, player in sleeper_players.items():
        if normalize_name(_sleeper_display_name(player)) == target_name:
            exact.append((player_id, player))

    position_matches = [
        pair for pair in exact if target_position in _sleeper_positions(pair[1])
    ]

    if target_team:
        team_position_matches = [
            pair for pair in position_matches
            if normalize_team(pair[1].get("team")) == target_team
        ]
        if team_position_matches:
            return team_position_matches[0]

        team_matches = [
            pair for pair in exact
            if normalize_team(pair[1].get("team")) == target_team
        ]
        if team_matches:
            return team_matches[0]

    if position_matches:
        return position_matches[0]
    if exact:
        return exact[0]

    best = None
    best_score = 0.0
    for player_id, player in sleeper_players.items():
        candidate = normalize_name(_sleeper_display_name(player))
        if not candidate:
            continue
        score = SequenceMatcher(None, target_name, candidate).ratio()
        if target_position not in _sleeper_positions(player):
            score -= 0.08
        if target_team and normalize_team(player.get("team")) == target_team:
            score += 0.10
        if score > best_score:
            best_score = score
            best = (player_id, player)

    return best if best and best_score >= 0.82 else None


def score_offense(stats):
    total = num(stats.get("pass_yd")) / 25.0
    total += num(stats.get("pass_td")) * 6.0
    total += num(stats.get("pass_int")) * -3.0
    total += 4.0 if num(stats.get("pass_yd")) >= 350 else 0.0

    rush_yd = num(stats.get("rush_yd"))
    total += rush_yd / 10.0
    total += num(stats.get("rush_td")) * 6.0
    if rush_yd >= 150:
        total += 4.0
    elif rush_yd >= 125:
        total += 3.0

    rec_yd = num(stats.get("rec_yd"))
    total += num(stats.get("rec"))
    total += rec_yd / 10.0
    total += num(stats.get("rec_td")) * 6.0
    if rec_yd >= 150:
        total += 3.0
    elif rec_yd >= 125:
        total += 2.0

    total += (num(stats.get("pass_2pt")) + num(stats.get("rush_2pt")) + num(stats.get("rec_2pt"))) * 2.0
    total += num(stats.get("fum_lost")) * -2.0
    total += (num(stats.get("st_td")) + num(stats.get("ret_td")) + num(stats.get("fum_rec_td")) + num(stats.get("off_fum_rec_td"))) * 6.0
    return round(total, 2)


def score_kicker(stats):
    total = 0.0
    total += num(stats.get("fgm_0_19")) * 3
    total += num(stats.get("fgm_20_29")) * 3
    total += num(stats.get("fgm_30_39")) * 3
    total += num(stats.get("fgm_40_49")) * 4
    total += num(stats.get("fgm_50_plus", stats.get("fgm_50_59"))) * 5
    total += num(stats.get("fgm_60p")) * 5
    total += num(stats.get("xpm"))
    total += num(stats.get("fgmiss")) * -1
    total += num(stats.get("xpmiss")) * -1
    return round(total, 2)


def points_allowed(stats):
    for key in ("pts_allow", "pts_allowed", "points_allowed", "def_pts_allow", "pts_allow_total"):
        if key in stats:
            return num(stats[key])
    return None


def score_defense(stats):
    total = 0.0
    total += num(stats.get("def_sack", stats.get("sack"))) * 1
    total += num(stats.get("def_int", stats.get("int"))) * 2
    total += num(stats.get("def_fum_rec", stats.get("fum_rec"))) * 2
    total += num(stats.get("def_td", stats.get("td"))) * 6
    total += num(stats.get("safe", stats.get("safety"))) * 2
    total += num(stats.get("blk_kick", stats.get("block_kick"))) * 2
    total += num(stats.get("st_td")) * 6
    total += num(stats.get("def_st_td")) * 6
    total += num(stats.get("extra_point_returned")) * 2

    pa = points_allowed(stats)
    if pa is not None:
        if pa <= 0:
            total += 10
        elif pa <= 6:
            total += 7
        elif pa <= 13:
            total += 4
        elif pa <= 20:
            total += 1
        elif pa <= 27:
            total += 0
        elif pa <= 34:
            total -= 1
        else:
            total -= 4
    return round(total, 2)


def score_stats(stats, position):
    pos = str(position or "").upper()
    if pos == "K":
        return score_kicker(stats)
    if pos in {"DEF", "DST", "D/ST"}:
        return score_defense(stats)
    return score_offense(stats)


def game_status_for(team, game_lookup):
    game = game_lookup.get(str(team or "").upper())
    if not game:
        return {"opponent": "", "game_time": "", "game_status": "", "status_detail": ""}
    return {
        "opponent": game.get("opponent", ""),
        "game_time": game.get("game_time", ""),
        "game_status": game.get("game_status", ""),
        "status_detail": game.get("status_detail", ""),
    }


def player_state(game):
    status = str(game.get("game_status") or "").upper()
    detail = str(game.get("status_detail") or "").upper()
    finished = "FINAL" in status or "COMPLETED" in status or "FINAL" in detail or "END" in detail
    live = not finished and ("LIVE" in status or "IN_PROGRESS" in status)
    return finished, live


def build_player(manual, index, player_id, sleeper_player, projection_row, actual_row, game_lookup):
    projection_stats = projection_row.get("stats", projection_row) if projection_row else {}
    actual_stats = actual_row.get("stats", actual_row) if actual_row else {}

    projection = score_stats(projection_stats, manual["position"])
    has_played = num(actual_stats.get("gp")) > 0 or num(actual_stats.get("g")) > 0
    actual = score_stats(actual_stats, manual["position"]) if has_played else None

    team = str(manual.get("team") or sleeper_player.get("team") or "").upper()
    game = game_status_for(team, game_lookup)
    finished, live = player_state(game)

    return {
        "id": f"yahoo-{index}-{player_id}",
        "name": manual["name"],
        "matched_name": _sleeper_display_name(sleeper_player),
        "position": manual["position"],
        "roster_slot": manual["roster_slot"],
        "slot": manual["position"],
        "team": team,
        "nfl_team": team,
        "pro_team_id": team,
        "projection": round(projection, 2),
        "projected": round(projection, 2),
        "actual": round(actual, 2) if actual is not None else None,
        "points": round(actual if actual is not None else projection, 2),
        "opponent": game["opponent"],
        "game_time": game["game_time"],
        "game_status": game["game_status"],
        "status_detail": game["status_detail"],
        "injury": sleeper_player.get("injury_status") or "",
        "finished": finished,
        "live": live,
    }


def best_one(players, position):
    options = [p for p in players if p["position"] == position and p.get("projection") is not None]
    return max(options, key=lambda p: p["projection"], default=None)


def top_n(players, position, n):
    options = [p for p in players if p["position"] == position and p.get("projection") is not None]
    return sorted(options, key=lambda p: p["projection"], reverse=True)[:n]


def optimize_lineup(players):
    active_pool = [p for p in players if p.get("roster_slot") != "IR"]

    qb = best_one(active_pool, "QB")
    kicker = best_one(active_pool, "K")
    defense = best_one(active_pool, "DEF")
    rbs = top_n(active_pool, "RB", 2)
    wrs = top_n(active_pool, "WR", 2)

    selected_ids = {p["id"] for p in (qb, kicker, defense) if p}
    selected_ids.update(p["id"] for p in rbs)
    selected_ids.update(p["id"] for p in wrs)

    flex_pool = sorted(
        [p for p in active_pool if p["position"] in FLEX_POSITIONS and p["id"] not in selected_ids],
        key=lambda p: p["projection"],
        reverse=True,
    )
    flexes = flex_pool[:3]

    starters = []
    if qb:
        starters.append({**qb, "slot": "QB"})
    starters.extend({**p, "slot": "RB"} for p in rbs)
    starters.extend({**p, "slot": "WR"} for p in wrs)
    starters.extend({**p, "slot": "FLEX"} for p in flexes)
    if kicker:
        starters.append({**kicker, "slot": "K"})
    if defense:
        starters.append({**defense, "slot": "DEF"})

    order = {"QB": 0, "RB": 1, "WR": 3, "FLEX": 5, "K": 8, "DEF": 9}
    starters.sort(key=lambda p: order.get(p["slot"], 20))

    selected_ids = {p["id"] for p in starters}
    alternatives = []

    groups = [
        ("QB", [p for p in active_pool if p["position"] == "QB"], [p for p in starters if p["slot"] == "QB"]),
        ("RB", [p for p in active_pool if p["position"] == "RB"], rbs),
        ("WR", [p for p in active_pool if p["position"] == "WR"], wrs),
        ("FLEX", [p for p in active_pool if p["position"] in FLEX_POSITIONS], flexes),
        ("K", [p for p in active_pool if p["position"] == "K"], [p for p in starters if p["slot"] == "K"]),
        ("DEF", [p for p in active_pool if p["position"] == "DEF"], [p for p in starters if p["slot"] == "DEF"]),
    ]

    for label, candidates, selected_group in groups:
        if not selected_group:
            continue
        candidates = sorted(
            [p for p in candidates if p["id"] not in selected_ids],
            key=lambda p: p["projection"],
            reverse=True,
        )
        if not candidates:
            continue
        lowest = min(selected_group, key=lambda p: p["projection"])
        next_player = candidates[0]
        if lowest["projection"] - next_player["projection"] <= CLOSE_THRESHOLD:
            alternatives.append({**next_player, "slot": label, "close_to": lowest["name"]})

    projected_total = 0.0

    for player in starters:
        if player.get("finished") and player.get("actual") is not None:
            projected_total += num(player["actual"])
        else:
            projected_total += num(player.get("projection"))

    return {
        "starters": starters,
        "alternatives": alternatives,
        "projected_total": round(projected_total, 2),
    }


def build_manual_yahoo(game_lookup):
    week = int(get_sleeper_state().get("week") or 1)
    sleeper_players = get_sleeper_players()
    projection_data = get_projection_data(2026, week)
    actual_data = get_stats_data(2026, week)
    projection_rows = projection_rows_by_player(projection_data)
    actual_rows = projection_rows_by_player(actual_data)

    roster_output = []
    unmatched = []

    for index, manual in enumerate(YAHOO_ROSTER):
        match = find_sleeper_player(manual, sleeper_players)
        if not match:
            unmatched.append(manual["name"])
            continue

        player_id, sleeper_player = match
        player = build_player(
            manual,
            index,
            player_id,
            sleeper_player,
            projection_rows.get(str(player_id), {}),
            actual_rows.get(str(player_id), {}),
            game_lookup,
        )
        roster_output.append(player)

    result = optimize_lineup(roster_output)

    return {
        "platform": "Yahoo",
        "manual": True,
        "week": week,
        "league_name": "Moore Nix Pics",
        "starters": result["starters"],
        "alternatives": result["alternatives"],
        "projected_total": result["projected_total"],
        "roster": roster_output,
        "unmatched": unmatched,
        "close_threshold": CLOSE_THRESHOLD,
    }
