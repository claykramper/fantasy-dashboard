import time
from datetime import datetime, timedelta

import requests

from config import ESPN_SCOREBOARD_URL, LOCAL_TIMEZONE


def get_nfl_schedule():
    games = []

    today = datetime.now(LOCAL_TIMEZONE).date()

    # Fetch recent past games as well as upcoming games.
    # This is important for the "Games Completed" filter.
    #
    # We go back 7 days so every game from the current fantasy
    # week is still available in the lookup.
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

            kickoff_text = (
                event.get("date")
                or competition.get("date")
            )

            if not kickoff_text:
                continue

            try:
                kickoff = datetime.fromisoformat(
                    kickoff_text.replace(
                        "Z",
                        "+00:00",
                    )
                )
            except ValueError:
                continue

            status_obj = competition.get(
                "status",
                {}
            )

            status_type = status_obj.get(
                "type",
                {}
            )

            games.append(
                {
                    "id": str(
                        event.get("id")
                    ),

                    "kickoff": kickoff,

                    "home": {
                        "id": str(
                            home.get("id", "")
                        ),
                        "abbreviation": (
                            home
                            .get("team", {})
                            .get(
                                "abbreviation",
                                "",
                            )
                        ),
                        "display_name": (
                            home
                            .get("team", {})
                            .get(
                                "displayName",
                                "",
                            )
                        ),
                    },

                    "away": {
                        "id": str(
                            away.get("id", "")
                        ),
                        "abbreviation": (
                            away
                            .get("team", {})
                            .get(
                                "abbreviation",
                                "",
                            )
                        ),
                        "display_name": (
                            away
                            .get("team", {})
                            .get(
                                "displayName",
                                "",
                            )
                        ),
                    },

                    "status": status_type.get(
                        "name",
                        "",
                    ),

                    "status_detail": status_type.get(
                        "detail",
                        status_type.get(
                            "shortDetail",
                            "",
                        ),
                    ),
                }
            )

    # Avoid duplicates just in case the API returns
    # the same event more than once.
    unique_games = {}

    for game in games:
        unique_games[game["id"]] = game

    games = list(unique_games.values())

    games.sort(
        key=lambda game: game["kickoff"]
    )

    return games


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


def format_slate_label(kickoff):
    # Example:
    # Sun 12:00 PM
    local = kickoff.astimezone(
        LOCAL_TIMEZONE
    )

    return local.strftime(
        "%a %I:%M %p"
    ).lstrip("0")


def format_game_time(kickoff):
    local = kickoff.astimezone(
        LOCAL_TIMEZONE
    )

    return local.strftime(
        "%I:%M %p"
    ).lstrip("0")


def build_slate_data(games):
    now = datetime.now(
        LOCAL_TIMEZONE
    )

    output = []

    for index, slate in enumerate(
        group_games_into_slates(games)
    ):
        kickoff = slate[
            "kickoff"
        ].astimezone(
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

                "timestamp": (
                    slate["kickoff"]
                    .timestamp()
                ),

                "is_upcoming": (
                    slate["kickoff"] > now
                ),

                "games": [
                    {
                        "id": game["id"],

                        "away": game["away"][
                            "abbreviation"
                        ],

                        "home": game["home"][
                            "abbreviation"
                        ],

                        "away_id": game["away"][
                            "id"
                        ],

                        "home_id": game["home"][
                            "id"
                        ],

                        "kickoff": game[
                            "kickoff"
                        ].isoformat(),

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

                    for game in slate["games"]
                ],
            }
        )

    return output


def get_next_slate_index(slates):
    now = time.time()

    for slate in slates:
        if slate["timestamp"] > now:
            return slate["id"]

    return None


def build_game_lookup(nfl_games):
    lookup = {}

    for game in nfl_games:
        home_id = str(
            game["home"]["id"]
        )

        away_id = str(
            game["away"]["id"]
        )

        kickoff = (
            game["kickoff"]
            .astimezone(
                LOCAL_TIMEZONE
            )
        )

        home = {
            "team": game["home"][
                "abbreviation"
            ],

            "opponent": game["away"][
                "abbreviation"
            ],

            "opponent_id": away_id,

            "home": True,

            "kickoff": kickoff,

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

        away = {
            "team": game["away"][
                "abbreviation"
            ],

            "opponent": game["home"][
                "abbreviation"
            ],

            "opponent_id": home_id,

            "home": False,

            "kickoff": kickoff,

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

        # ESPN team ID lookup
        lookup[home_id] = home
        lookup[away_id] = away

        # NFL abbreviation lookup
        lookup[
            game["home"]["abbreviation"].upper()
        ] = home

        lookup[
            game["away"]["abbreviation"].upper()
        ] = away

    return lookup