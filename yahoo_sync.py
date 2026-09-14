import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


HTML_FILE = Path("yahoo_matchup.html")
OUTPUT_FILE = Path("yahoo_test.json")


def clean_text(element):
    if element is None:
        return None

    text = element.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip() or None


def parse_number(text):
    if text is None:
        return None

    text = text.strip().replace(",", "")
    if text in {"", "-", "\u2013", "\u2014"}:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def extract_position(cell):
    if cell is None:
        return None

    position_element = cell.find(class_="pos-label")
    if position_element:
        value = position_element.get("data-pos")
        if value:
            return value.strip()

        text = clean_text(position_element)
        if text:
            return text

    text = clean_text(cell)
    if text and len(text) <= 10:
        return text

    return None


def extract_player(cell):
    if cell is None:
        return None

    player_link = cell.find("a", attrs={"data-ys-playerid": True})
    if player_link is None:
        return None

    player_id = player_link.get("data-ys-playerid")
    name = player_link.get("title") or clean_text(player_link)
    if not player_id or not name:
        return None

    team = None
    position = None
    for element in cell.find_all(["div", "span"]):
        text = clean_text(element)
        if not text:
            continue

        match = re.match(r"^([A-Z]{2,3})\s*-\s*([A-Z/]+)$", text)
        if match:
            team = match.group(1)
            position = match.group(2)
            break

    game_status = None
    game_url = None
    game_status_element = cell.find(class_="ysf-game-status")
    if game_status_element:
        game_link = game_status_element.find("a")
        if game_link:
            game_status = clean_text(game_link)
            game_url = game_link.get("href")
        else:
            game_status = clean_text(game_status_element)

    injury = None
    player_status = cell.find(class_="ysf-player-status")
    if player_status:
        injury = player_status.get("title")
        if not injury:
            for element in player_status.find_all(attrs={"title": True}):
                injury = element.get("title")
                if injury:
                    break

    return {
        "player_id": str(player_id),
        "name": name,
        "team": team,
        "position": position,
        "injury": injury,
        "game_status": game_status,
        "game_url": game_url,
    }


def parse_matchup_row(row, section):
    cells = row.find_all("td", recursive=False)
    if len(cells) < 10:
        return None, None

    left_player = extract_player(cells[1])
    right_player = extract_player(cells[9])

    if left_player:
        left_player["roster_position"] = (
            extract_position(cells[5]) or left_player["position"]
        )
        left_player["projected_points"] = parse_number(clean_text(cells[2]))
        left_player["fantasy_points"] = parse_number(clean_text(cells[3]))
        left_player["section"] = section

    if right_player:
        right_player["roster_position"] = (
            extract_position(cells[6]) or right_player["position"]
        )
        right_player["fantasy_points"] = parse_number(clean_text(cells[7]))
        right_player["projected_points"] = parse_number(clean_text(cells[8]))
        right_player["section"] = section

    return left_player, right_player


def parse_table(table, section):
    my_players = []
    opponent_players = []
    tbody = table.find("tbody")
    if tbody is None:
        return {
            "my_players": my_players,
            "opponent_players": opponent_players,
        }

    for row in tbody.find_all("tr", recursive=False):
        left_player, right_player = parse_matchup_row(row, section)
        if left_player:
            my_players.append(left_player)
        if right_player:
            opponent_players.append(right_player)

    return {
        "my_players": my_players,
        "opponent_players": opponent_players,
    }


def parse_total_row(table):
    for row in table.find_all("tr"):
        text = clean_text(row)
        if not text or "TOTAL" not in text.upper():
            continue

        cells = row.find_all("td", recursive=False)
        if len(cells) < 9:
            continue

        return {
            "my_projected_points": parse_number(clean_text(cells[2])),
            "my_fantasy_points": parse_number(clean_text(cells[3])),
            "opponent_fantasy_points": parse_number(clean_text(cells[7])),
            "opponent_projected_points": parse_number(clean_text(cells[8])),
        }

    return {
        "my_projected_points": None,
        "my_fantasy_points": None,
        "opponent_fantasy_points": None,
        "opponent_projected_points": None,
    }


def extract_json_variable(html, variable):
    pattern = (
        rf'"{re.escape(variable)}"\s*:\s*'
        rf'(?:"([^"]*)"|([-+]?\d+(?:\.\d+)?))'
    )
    match = re.search(pattern, html)
    if not match:
        return None

    if match.group(1) is not None:
        return match.group(1)
    return match.group(2)


def extract_json_number(html, variable):
    return parse_number(extract_json_variable(html, variable))


def extract_matchup_metadata(html):
    return {
        "team_name": "Moore Nix Pics",
        "opponent_name": extract_json_variable(html, "varPROppTeamName"),
        "opponent_fantasy_points": extract_json_number(
            html, "varPROppTeamWeekScore"
        ),
        "opponent_projected_points": extract_json_number(
            html, "varPROppTeamWeekProjectedPts"
        ),
        "my_projected_points": extract_json_number(
            html, "varPRCurrTeamWeekProjectedPts"
        ),
    }


def find_matchup_tables(soup):
    return soup.find_all("table", id=re.compile(r"^statTable\d*$"))


def find_starter_and_bench_tables(soup):
    tables = find_matchup_tables(soup)
    if not tables:
        raise RuntimeError("Could not find any Yahoo statTable elements.")

    starter_table = None
    bench_table = None
    for table in tables:
        table_id = table.get("id", "")
        if table_id == "statTable1":
            starter_table = table
        elif table_id == "statTable2":
            bench_table = table

    if starter_table is None:
        for table in tables:
            parent = table.parent
            if parent and parent.get("id") == "matchupcontent1":
                starter_table = table
                break

    if bench_table is None:
        bench_container = soup.find(id="bench-table")
        if bench_container:
            bench_table = bench_container.find("table")

    return starter_table, bench_table


def parse_yahoo_matchup():
    if not HTML_FILE.exists():
        raise FileNotFoundError("Could not find yahoo_matchup.html")

    html = HTML_FILE.read_text(encoding="utf-8", errors="replace")
    print(f"Loaded Yahoo HTML: {len(html):,} characters")

    soup = BeautifulSoup(html, "html.parser")
    starter_table, bench_table = find_starter_and_bench_tables(soup)
    if starter_table is None:
        raise RuntimeError("Could not identify the Yahoo starter matchup table.")

    print(f"Found starter table: YES ({starter_table.get('id')})")
    if bench_table:
        print(f"Found bench table: YES ({bench_table.get('id')})")
    else:
        print("Found bench table: NO")

    starters = parse_table(starter_table, "starter")
    bench = {"my_players": [], "opponent_players": []}
    if bench_table:
        bench = parse_table(bench_table, "bench")

    totals = parse_total_row(starter_table)
    metadata = extract_matchup_metadata(html)
    my_projection = totals["my_projected_points"]
    opponent_projection = totals["opponent_projected_points"]
    opponent_score = totals["opponent_fantasy_points"]

    if my_projection is None:
        my_projection = metadata["my_projected_points"]
    if opponent_projection is None:
        opponent_projection = metadata["opponent_projected_points"]
    if opponent_score is None:
        opponent_score = metadata["opponent_fantasy_points"]

    return {
        "platform": "yahoo",
        "league_name": "Protect Ya Neck",
        "league_id": "951434",
        "team_name": metadata["team_name"],
        "opponent_name": metadata["opponent_name"],
        "week": 1,
        "my_score": totals["my_fantasy_points"],
        "opp_score": opponent_score,
        "my_projected_score": my_projection,
        "opp_projected_score": opponent_projection,
        "starters": starters["my_players"],
        "opponent_starters": starters["opponent_players"],
        "bench": bench["my_players"],
        "opponent_bench": bench["opponent_players"],
    }


def print_players(title, players):
    print()
    print(title)
    print("-" * 100)
    for player in players:
        position = player.get("roster_position") or player.get("position") or "?"
        fantasy_points = player.get("fantasy_points")
        projected_points = player.get("projected_points")
        line = (
            f"{position:<7} {player['name']:<25} "
            f"FP={str(fantasy_points):>6} Proj={str(projected_points):>6}"
        )
        if player.get("injury"):
            line += f"  [{player['injury']}]"
        if player.get("game_status"):
            line += f"  {player['game_status']}"
        print(line)


def main():
    result = parse_yahoo_matchup()
    OUTPUT_FILE.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print("YAHOO MATCHUP PARSER TEST")
    print("=" * 100)
    print(f"My team:        {result['team_name']}")
    print(f"Opponent:       {result['opponent_name']}")
    print(f"My score:       {result['my_score']}")
    print(f"Opponent score: {result['opp_score']}")
    print(f"My projection:  {result['my_projected_score']}")
    print(f"Opp projection: {result['opp_projected_score']}")
    print(f"My starters:       {len(result['starters'])}")
    print(f"Opponent starters: {len(result['opponent_starters'])}")
    print(f"My bench:           {len(result['bench'])}")
    print(f"Opponent bench:     {len(result['opponent_bench'])}")

    print_players("MY STARTERS", result["starters"])
    print_players("OPPONENT STARTERS", result["opponent_starters"])
    print_players("MY BENCH", result["bench"])
    print_players("OPPONENT BENCH", result["opponent_bench"])

    print()
    print("=" * 100)
    print(f"JSON saved to: {OUTPUT_FILE}")
    print("=" * 100)


if __name__ == "__main__":
    main()
