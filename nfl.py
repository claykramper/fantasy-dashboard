import time
from datetime import datetime, timedelta, time as dt_time

import requests

from config import ESPN_SCOREBOARD_URL, LOCAL_TIMEZONE


# ============================================================
# TIME / FANTASY-WEEK HELPERS
# ============================================================

def parse_kickoff(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None

    return parsed.astimezone(LOCAL_TIMEZONE)


def format_slate_label(kickoff):
    local = kickoff.astimezone(LOCAL_TIMEZONE)
    return local.strftime("%a %I:%M %p").lstrip("0")


def format_game_time(kickoff):
    local = kickoff.astimezone(LOCAL_TIMEZONE)
    return local.strftime("%I:%M %p").lstrip("0")


def monday_start_for(date_value):
    """Return the Monday 12:00 AM Central that owns this date."""
    days_since_monday = date_value.weekday()
    return date_value - timedelta(days=days_since_monday)


def _is_final(game):
    status = str(game.get("status") or "").upper()
    detail = str(game.get("status_detail") or "").upper()

    return (
        "FINAL" in status
        or "COMPLETED" in status
        or "FINAL" in detail
        or "END" in detail
    )


def current_fantasy_week_window(now=None, games=None):
    """
    Fantasy weeks run Monday morning -> Monday night.

    We intentionally do NOT advance to the next week merely because
    the clock reaches Monday. The current fantasy week remains active
    until every NFL game scheduled for Monday is final.

    Once Monday's games are finished, the next Monday becomes the
    current week immediately. In normal NFL scheduling this means the
    rollover happens immediately after Monday Night Football ends.

    Returns:
        week_start_datetime,
        week_end_datetime,
        week_key
    """
    now = now or datetime.now(LOCAL_TIMEZONE)
    local_now = now.astimezone(LOCAL_TIMEZONE)

    today = local_now.date()
    week_start_date = monday_start_for(today)
    week_start = datetime.combine(
        week_start_date,
        dt_time.min,
        tzinfo=LOCAL_TIMEZONE,
    )
    next_week_start = week_start + timedelta(days=7)

    # Before Monday at 12:00 AM -> straightforward current week.
    if local_now < next_week_start:
        return (
            week_start,
            next_week_start,
            week_start.strftime("%Y-%m-%d"),
        )

    # At/after Monday midnight, determine whether Monday's games are
    # finished. If they are not, keep the previous fantasy week alive.
    monday_games = []

    if games:
        for game in games:
            kickoff = game.get("kickoff")
            if not kickoff:
                continue

            local_kickoff = kickoff.astimezone(
                LOCAL_TIMEZONE
            )

            if local_kickoff.date() == today:
                monday_games.append(game)

    if monday_games and not all(_is_final(game) for game in monday_games):
        return (
            week_start,
            next_week_start,
            week_start.strftime("%Y-%m-%d"),
        )

    # No Monday games or all Monday games are final: roll forward.
    rolled_start = next_week_start
    rolled_end = rolled_start + timedelta(days=7)

    return (
        rolled_start,
        rolled_end,
        rolled_start.strftime("%Y-%m-%d"),
    )


def filter_games_to_current_fantasy_week(games, now=None):
    """Return only games belonging to the current fantasy week."""
    week_start, week_end, _ = current_fantasy_week_window(
        now=now,
        games=games,
    )

    output = []

    for game in games:
        kickoff = game.get("kickoff")
        if not kickoff:
            continue

        local_kickoff = kickoff.astimezone(
            LOCAL_TIMEZONE
        )

        if week_start <= local_kickoff < week_end:
            output.append(game)

    return output


# ============================================================
# NFL SCHEDULE
# ============================================================

def get_nfl_schedule():
    """
    Fetch enough history for Games Completed and enough future
    schedule for the current fantasy week.

    The returned list is then filtered to ONLY the active
    Monday-to-Monday fantasy week.
    """
    games = []

    today = datetime.now(
        LOCAL_TIMEZONE
    ).date()

    # Load recent past + future so we can determine the Monday
    # rollover and retain current-week completed games.
    for offset in range(-7, 9):
        day = today + timedelta(days=offset)

        try:
            response = requests.get(
                ESPN_SCOREBOARD_URL,
                params={
                    "dates": day.strftime("%Y%m%d")
                },
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            continue

        for event in data.get("events", []):
            competitions = event.get("competitions", [])
            if not competitions:
                continue

            competition = competitions[0]
            competitors = competition.get("competitors", [])

            if len(competitors) < 2:
                continue

            home = next(
                (
                    competitor
                    for competitor in competitors
                    if competitor.get("homeAway") == "home"
                ),
                competitors[0],
            )

            away = next(
                (
                    competitor
                    for competitor in competitors
                    if competitor.get("homeAway") == "away"
                ),
                competitors[1],
            )

            # Competition date is the most specific kickoff value.
            kickoff_text = (
                competition.get("date")
                or event.get("date")
            )

            kickoff = parse_kickoff(kickoff_text)
            if kickoff is None:
                continue

            status_obj = competition.get("status", {})
            status_type = status_obj.get("type", {})

            home_team = home.get("team", {})
            away_team = away.get("team", {})

            games.append(
                {
                    "id": str(event.get("id")),
                    "kickoff": kickoff,
                    "home": {
                        "id": str(home.get("id", "")),
                        "abbreviation": home_team.get(
                            "abbreviation", ""
                        ),
                        "display_name": home_team.get(
                            "displayName", ""
                        ),
                    },
                    "away": {
                        "id": str(away.get("id", "")),
                        "abbreviation": away_team.get(
                            "abbreviation", ""
                        ),
                        "display_name": away_team.get(
                            "displayName", ""
                        ),
                    },
                    "status": status_type.get("name", ""),
                    "status_detail": status_type.get(
                        "detail",
                        status_type.get(
                            "shortDetail", ""
                        ),
                    ),
                }
            )

    # Deduplicate events.
    unique_games = {
        game["id"]: game
        for game in games
    }

    games = sorted(
        unique_games.values(),
        key=lambda game: game["kickoff"],
    )

    return filter_games_to_current_fantasy_week(
        games
    )


# ============================================================
# SLATE GROUPING
# ============================================================

def group_games_into_slates(games):
    if not games:
        return []

    games = sorted(
        games,
        key=lambda game: game["kickoff"],
    )

    slates = []
    current = None

    for game in games:
        if current is None:
            current = {
                "kickoff": game["kickoff"],
                "games": [game],
            }
            slates.append(current)
            continue

        elapsed = (
            game["kickoff"]
            - current["kickoff"]
        ).total_seconds()

        if elapsed <= 45 * 60:
            current["games"].append(game)
        else:
            current = {
                "kickoff": game["kickoff"],
                "games": [game],
            }
            slates.append(current)

    return slates


# ============================================================
# FRONT-END SLATE DATA
# ============================================================

def build_slate_data(games):
    now = datetime.now(LOCAL_TIMEZONE)
    _, _, week_key = current_fantasy_week_window(
        now=now,
        games=games,
    )

    output = []

    for index, slate in enumerate(
        group_games_into_slates(games)
    ):
        kickoff = slate["kickoff"].astimezone(
            LOCAL_TIMEZONE
        )

        output.append(
            {
                "id": index,
                "label": format_slate_label(
                    slate["kickoff"]
                ),
                "date": kickoff.strftime(
                    "%Y-%m-%d"
                ),
                "kickoff": kickoff.isoformat(),
                "timestamp": slate["kickoff"].timestamp(),
                "is_upcoming": slate["kickoff"] > now,
                "games": [
                    {
                        "id": game["id"],
                        "away": game["away"]["abbreviation"],
                        "home": game["home"]["abbreviation"],
                        "away_id": game["away"]["id"],
                        "home_id": game["home"]["id"],
                        "kickoff": game["kickoff"].isoformat(),
                        "game_time": format_game_time(
                            game["kickoff"]
                        ),
                        "game_status": game["status"],
                        "status_detail": game["status_detail"],
                    }
                    for game in slate["games"]
                ],
            }
        )

    return output, week_key


# ============================================================
# DEFAULT SLATE
# ============================================================

def get_next_slate_index(slates):
    now = time.time()

    for slate in slates:
        if slate["timestamp"] > now:
            return slate["id"]

    return None


# ============================================================
# GAME LOOKUP
# ============================================================

def build_game_lookup(nfl_games):
    """
    nfl_games contains ONLY the current fantasy week.

    That is intentional: a player can never accidentally inherit
    another week's kickoff or status, and bye-week players do not
    get matched against a future/previous game.
    """
    lookup = {}

    now = datetime.now(LOCAL_TIMEZONE)

    for game in nfl_games:
        kickoff = game["kickoff"].astimezone(
            LOCAL_TIMEZONE
        )

        home_id = str(game["home"]["id"])
        away_id = str(game["away"]["id"])

        home_abbrev = game["home"]["abbreviation"]
        away_abbrev = game["away"]["abbreviation"]

        home_data = {
            "team": home_abbrev,
            "opponent": away_abbrev,
            "opponent_id": away_id,
            "home": True,
            "kickoff": kickoff,
            "game_time": format_game_time(kickoff),
            "game_status": game["status"],
            "status_detail": game["status_detail"],
        }

        away_data = {
            "team": away_abbrev,
            "opponent": home_abbrev,
            "opponent_id": home_id,
            "home": False,
            "kickoff": kickoff,
            "game_time": format_game_time(kickoff),
            "game_status": game["status"],
            "status_detail": game["status_detail"],
        }

        # There is only one game per team in the current fantasy
        # week, so these mappings cannot be overwritten by a future
        # week anymore.
        lookup[home_id] = home_data
        lookup[away_id] = away_data
        lookup[home_abbrev.upper()] = home_data
        lookup[away_abbrev.upper()] = away_data

    return lookup
