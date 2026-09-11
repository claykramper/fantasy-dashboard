from __future__ import annotations

from itertools import product

from sleeper import get_projection_data, get_sleeper_players, get_sleeper_state

# ============================================================
# MANUAL YAHOO ROSTER
#
# Update this list whenever your Yahoo roster changes.
# roster_slot is informational only; BN players are still
# eligible to become projected starters.
# IR players are excluded from the optimizer.
# ============================================================

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

# Yahoo roster rules supplied by the user.
ROSTER_REQUIREMENTS = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "FLEX": 3,
    "K": 1,
    "DEF": 1,
}

FLEX_POSITIONS = {"RB", "WR", "TE"}
CLOSE_THRESHOLD = 1.5


# ============================================================
# YAHOO SCORING
# ============================================================


def num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def score_offense(stats):
    """Yahoo league scoring supplied by the user."""
    total = 0.0

    # Passing: 25 yards/point, 6 TD, -3 INT.
    total += num(stats.get("pass_yd")) / 25.0
    total += num(stats.get("pass_td")) * 6.0
    total += num(stats.get("pass_int")) * -3.0

    # 350+ passing yards bonus.
    if num(stats.get("pass_yd")) >= 350:
        total += 4.0

    # Rushing: 10 yards/point, 6 TD.
    rush_yd = num(stats.get("rush_yd"))
    total += rush_yd / 10.0
    total += num(stats.get("rush_td")) * 6.0

    # Yahoo threshold bonus is the applicable tier, not cumulative.
    if rush_yd >= 150:
        total += 4.0
    elif rush_yd >= 125:
        total += 3.0

    # Receiving: full PPR, 10 yards/point, 6 TD.
    rec_yd = num(stats.get("rec_yd"))
    total += num(stats.get("rec")) * 1.0
    total += rec_yd / 10.0
    total += num(stats.get("rec_td")) * 6.0

    if rec_yd >= 150:
        total += 3.0
    elif rec_yd >= 125:
        total += 2.0

    # Two point conversions and fumbles lost.
    total += num(stats.get("pass_2pt")) * 2.0
    total += num(stats.get("rush_2pt")) * 2.0
    total += num(stats.get("rec_2pt")) * 2.0
    total += num(stats.get("fum_lost")) * -2.0

    # Return TD / fumble return TD fields vary across feeds.
    total += num(stats.get("st_td")) * 6.0
    total += num(stats.get("ret_td")) * 6.0
    total += num(stats.get("fum_rec_td")) * 6.0
    total += num(stats.get("off_fum_rec_td")) * 6.0

    return round(total, 2)


def score_kicker(stats):
    total = 0.0

    total += num(stats.get("fgm_0_19")) * 3.0
    total += num(stats.get("fgm_20_29")) * 3.0
    total += num(stats.get("fgm_30_39")) * 3.0
    total += num(stats.get("fgm_40_49")) * 4.0
    total += num(stats.get("fgm_50_plus")) * 5.0
    total += num(stats.get("fgm_50_59")) * 5.0
    total += num(stats.get("fgm_60p")) * 5.0
    total += num(stats.get("xpm")) * 1.0

    return round(total, 2)


def points_allowed(stats):
    for key in ("pts_allow", "pts_allowed", "points_allowed"):
        if key in stats:
            return num(stats.get(key))

    # Some Sleeper feeds expose a direct points-allowed stat.
    for key in ("def_pts_allow", "pts_allow_total"):
        if key in stats:
            return num(stats.get(key))

    return None


def score_defense(stats):
    # Custom Yahoo D/ST scoring from the supplied league settings.
    total = 0.0

    total += num(stats.get("def_sack", stats.get("sack"))) * 3.0
    total += num(stats.get("def_int", stats.get("int"))) * 3.0
    total += num(stats.get("def_fum_rec", stats.get("fum_rec"))) * 3.0
    total += num(stats.get("def_td", stats.get("td"))) * 6.0
    total += num(stats.get("safe", stats.get("safety"))) * 2.0
    total += num(stats.get("blk_kick", stats.get("block_kick"))) * 2.0
    total += num(stats.get("st_td")) * 6.0
    total += num(stats.get("def_st_td")) * 6.0

    pa = points_allowed(stats)
    if pa is not None:
        if pa <= 0:
            total += 15.0
        elif pa <= 6:
            total += 12.0
        elif pa <= 13:
            total += 8.0
        elif pa <= 20:
            total += 3.0
        elif pa <= 27:
            total += 0.0
        elif pa <= 34:
            total -= 3.0
        else:
            total -= 6.0

    # Extra point returned.
    total += num(stats.get("extra_point_returned")) * 2.0
    total += num(stats.get("def_st_extra_point_returned")) * 2.0

    return round(total, 2)


def score_stats(stats, position):
    pos = str(position or "").upper()
    if pos == "K":
        return score_kicker(stats)
    if pos in {"DEF", "DST", "D/ST"}:
        return score_defense(stats)
    return score_offense(stats)


# ============================================================
# SLEEPER PLAYER MATCHING
# ============================================================


def normalize_name(name):
    replacements = {
        "’": "'",
        ".": "",
    }
    text = (name or "").strip().lower()
    for old, new in replacements.items():
        text = text.replace(old, new)
    return " ".join(text.split())


def find_sleeper_player(manual, sleeper_players):
    name = normalize_name(manual["name"])
    position = manual["position"].upper()
    team = str(manual.get("team") or "").upper()

    # Defense entries are team defenses rather than named players.
    if position == "DEF" and team:
        candidates = []
        for player_id, player in sleeper_players.items():
            if str(player.get("team") or "").upper() != team:
                continue
            player_pos = str(player.get("position") or "").upper()
            fantasy_positions = {
                str(p).upper()
                for p in (player.get("fantasy_positions") or [])
            }
            if player_pos in {"DEF", "DST"} or fantasy_positions & {"DEF", "DST", "D/ST"}:
                candidates.append((player_id, player))
        return candidates[0] if candidates else None

    # Exact normalized full-name match first.
    for player_id, player in sleeper_players.items():
        full_name = player.get("full_name") or " ".join(
            p for p in [player.get("first_name", ""), player.get("last_name", "")]
            if p
        )
        if normalize_name(full_name) != name:
            continue

        ppos = str(player.get("position") or "").upper()
        fantasy_positions = {
            str(p).upper() for p in (player.get("fantasy_positions") or [])
        }
        if position == ppos or position in fantasy_positions:
            return player_id, player

    # Position-agnostic exact name fallback.
    for player_id, player in sleeper_players.items():
        full_name = player.get("full_name") or " ".join(
            p for p in [player.get("first_name", ""), player.get("last_name", "")]
            if p
        )
        if normalize_name(full_name) == name:
            return player_id, player

    return None


def projection_rows_by_player(data):
    rows = {}
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and row.get("player_id") is not None:
                rows[str(row["player_id"])] = row
    elif isinstance(data, dict):
        for player_id, row in data.items():
            rows[str(player_id)] = row
    return rows


def game_status_for(team, game_lookup):
    game = game_lookup.get(str(team or "").upper())
    if not game:
        return {
            "opponent": "",
            "game_time": "",
            "game_status": "",
            "status_detail": "",
        }
    return {
        "opponent": game.get("opponent", ""),
        "game_time": game.get("game_time", ""),
        "game_status": game.get("game_status", ""),
        "status_detail": game.get("status_detail", ""),
    }


# ============================================================
# LINEUP OPTIMIZER
# ============================================================


def best_one(players, position):
    options = [p for p in players if p["position"] == position and p["projection"] is not None]
    options = sorted(options, key=lambda p: p["projection"], reverse=True)
    return options[0] if options else None


def top_n(players, position, n):
    options = [p for p in players if p["position"] == position and p["projection"] is not None]
    return sorted(options, key=lambda p: p["projection"], reverse=True)[:n]


def optimize_lineup(players):
    active_pool = [p for p in players if p.get("roster_slot") != "IR"]

    qb = best_one(active_pool, "QB")
    kicker = best_one(active_pool, "K")
    defense = best_one(active_pool, "DEF")

    rbs = top_n(active_pool, "RB", 2)
    wrs = top_n(active_pool, "WR", 2)

    selected_ids = {
        p["id"] for p in [qb, kicker, defense] if p is not None
    }
    selected_ids.update(p["id"] for p in rbs)
    selected_ids.update(p["id"] for p in wrs)

    flex_pool = [
        p for p in active_pool
        if p["position"] in FLEX_POSITIONS
        and p["id"] not in selected_ids
        and p.get("projection") is not None
    ]
    flexes = sorted(
        flex_pool,
        key=lambda p: p["projection"],
        reverse=True,
    )[:3]
    selected_ids.update(p["id"] for p in flexes)

    starters = []
    if qb:
        starters.append({**qb, "slot": "QB"})
    for p in rbs:
        starters.append({**p, "slot": "RB"})
    for p in wrs:
        starters.append({**p, "slot": "WR"})
    for p in flexes:
        starters.append({**p, "slot": "FLEX"})
    if kicker:
        starters.append({**kicker, "slot": "K"})
    if defense:
        starters.append({**defense, "slot": "DEF"})

    starters.sort(
        key=lambda p: {
            "QB": 0,
            "RB": 1,
            "WR": 3,
            "FLEX": 5,
            "K": 8,
            "DEF": 9,
        }.get(p["slot"], 20)
    )

    # Close alternatives by positional competition.
    alternatives = []

    def add_close_alternative(candidates, starters_for_group, label):
        candidates = [
            p for p in candidates
            if p["id"] not in selected_ids and p.get("projection") is not None
        ]
        candidates.sort(key=lambda p: p["projection"], reverse=True)
        if not candidates or not starters_for_group:
            return

        lowest = min(starters_for_group, key=lambda p: p["projection"])
        next_player = candidates[0]

        if lowest["projection"] - next_player["projection"] <= CLOSE_THRESHOLD:
            alternatives.append({
                **next_player,
                "slot": label,
                "close_to": lowest["name"],
            })

    add_close_alternative(
        [p for p in active_pool if p["position"] == "QB"],
        [p for p in starters if p["slot"] == "QB"],
        "QB",
    )
    add_close_alternative(
        [p for p in active_pool if p["position"] == "RB"],
        rbs,
        "RB",
    )
    add_close_alternative(
        [p for p in active_pool if p["position"] == "WR"],
        wrs,
        "WR",
    )
    add_close_alternative(
        [p for p in active_pool if p["position"] in FLEX_POSITIONS],
        flexes,
        "FLEX",
    )
    add_close_alternative(
        [p for p in active_pool if p["position"] == "K"],
        [p for p in starters if p["slot"] == "K"],
        "K",
    )
    add_close_alternative(
        [p for p in active_pool if p["position"] == "DEF"],
        [p for p in starters if p["slot"] == "DEF"],
        "DEF",
    )

    projected_total = round(
        sum(p["projection"] for p in starters if p.get("projection") is not None),
        2,
    )

    return {
        "starters": starters,
        "alternatives": alternatives,
        "projected_total": projected_total,
    }


# ============================================================
# BUILD THE MANUAL YAHOO SECTION
# ============================================================


def build_manual_yahoo(game_lookup):
    state = get_sleeper_state()
    week = int(state.get("week") or 1)

    sleeper_players = get_sleeper_players()
    projection_data = get_projection_data(2026, week)
    projection_rows = projection_rows_by_player(projection_data)

    roster_output = []
    unmatched = []

    for index, manual in enumerate(YAHOO_ROSTER):
        match = find_sleeper_player(
            manual,
            sleeper_players,
        )

        if not match:
            unmatched.append(manual["name"])
            continue

        player_id, sleeper_player = match
        row = projection_rows.get(str(player_id), {})
        stats = row.get("stats", row)

        team = str(
            manual.get("team")
            or sleeper_player.get("team")
            or row.get("team")
            or ""
        ).upper()

        projection = score_stats(
            stats,
            manual["position"],
        )

        game = game_status_for(
            team,
            game_lookup,
        )

        injury = sleeper_player.get("injury_status") or ""
        status_upper = str(game.get("game_status") or "").upper()
        finished = "FINAL" in status_upper or "COMPLETED" in status_upper
        live = "LIVE" in status_upper or "IN_PROGRESS" in status_upper

        roster_output.append(
            {
                "id": f"yahoo-{index}-{player_id}",
                "name": manual["name"],
                "position": manual["position"],
                "roster_slot": manual["roster_slot"],
                "team": team,
                "projection": round(projection, 2),
                "opponent": game["opponent"],
                "game_time": game["game_time"],
                "game_status": game["game_status"],
                "status_detail": game["status_detail"],
                "injury": injury,
                "finished": finished,
                "live": live,
            }
        )

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
