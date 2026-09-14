import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / 'leaguesync_browser_profile'
FULL_OUTPUT = BASE_DIR / 'leaguesync_dashboard.json'
YAHOO_OUTPUT = BASE_DIR / 'yahoo_leaguesync.json'
LEAGUESYNC_PAGE = 'https://www.leaguesync.app/'

load_dotenv(BASE_DIR / '.env')


def start_browser():
    print('Starting dedicated LeagueSync Firefox profile...')
    print('Profile folder: ' + str(PROFILE_DIR))
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument('-profile')
    options.add_argument(str(PROFILE_DIR))
    return webdriver.Firefox(options=options)


def get_dashboard_json(driver):
    print()
    print('Opening LeagueSync...')
    driver.get(LEAGUESYNC_PAGE)
    print()
    print('If you are not logged in, log into LeagueSync in the Firefox window.')
    print('After the LeagueSync dashboard is visible, return to this PowerShell window.')
    input('Press ENTER to retrieve the LeagueSync data...')
    print()
    print('Requesting authenticated LeagueSync dashboard data...')

    script = "return fetch('/api/me/dashboard', {credentials: 'include'}).then(async r => ({status: r.status, text: await r.text()}));"
    result = driver.execute_script(script)

    if not isinstance(result, dict):
        raise RuntimeError('LeagueSync browser request returned an unexpected result.')

    status = result.get('status')
    text = result.get('text', '')

    if status != 200:
        raise RuntimeError('LeagueSync returned HTTP ' + str(status) + ': ' + text[:500])

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError('LeagueSync returned invalid JSON: ' + str(exc))


def find_yahoo_league(data):
    if isinstance(data, list):
        leagues = data
    elif isinstance(data, dict):
        leagues = data.get('leagues')
        if leagues is None:
            raise RuntimeError("LeagueSync response does not contain a 'leagues' field.")
    else:
        raise RuntimeError('LeagueSync response has an unexpected JSON type: ' + type(data).__name__)

    if not isinstance(leagues, list):
        raise RuntimeError('LeagueSync league data is not a list.')

    for league in leagues:
        if isinstance(league, dict) and str(league.get('platform', '')).lower() == 'yahoo':
            return league

    raise RuntimeError('No Yahoo league was found in the LeagueSync response.')


def save_results(data, yahoo):
    FULL_OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    YAHOO_OUTPUT.write_text(json.dumps(yahoo, indent=2, ensure_ascii=False), encoding='utf-8')


def split_roster(roster):
    starters = []
    bench = []
    for player in roster or []:
        if not isinstance(player, dict):
            continue
        if player.get('status') == 'starter':
            starters.append(player)
        else:
            bench.append(player)
    return starters, bench


def print_players(title, players):
    print()
    print(title)
    print('-' * 90)
    for player in players:
        slot = player.get('slot') or player.get('position') or '?'
        name = player.get('name') or 'Unknown'
        points = player.get('points')
        projected = player.get('projected_points')
        status = player.get('status') or '?'
        injury = player.get('injury_status')
        game_status = player.get('game_status')
        opponent = player.get('opponent')
        line = '{:<7} {:<24} FP={:<7} Proj={:<7} Status={}'.format(
            str(slot), str(name), str(points), str(projected), str(status)
        )
        if injury:
            line += ' Injury=' + str(injury)
        if game_status:
            line += ' Game=' + str(game_status)
        if opponent:
            line += ' ' + str(opponent)
        print(line)


def print_summary(yahoo):
    matchup = yahoo.get('current_matchup')
    if not isinstance(matchup, dict):
        matchup = {}

    my_starters, my_bench = split_roster(yahoo.get('roster'))
    opp_starters, opp_bench = split_roster(matchup.get('opponent_roster'))

    print()
    print('=' * 90)
    print('LEAGUESYNC YAHOO SYNC')
    print('=' * 90)
    print('League:          ' + str(yahoo.get('league_name')))
    print('Team:            ' + str(yahoo.get('team_name')))
    print('Opponent:        ' + str(matchup.get('opponent')))
    print('Week:            ' + str(matchup.get('week')))
    print('My score:        ' + str(matchup.get('my_score')))
    print('Opponent score:  ' + str(matchup.get('opp_score')))
    print()
    print('My starters:       ' + str(len(my_starters)))
    print('My bench/IR:       ' + str(len(my_bench)))
    print('Opponent starters: ' + str(len(opp_starters)))
    print('Opponent bench:    ' + str(len(opp_bench)))
    print_players('MY STARTERS', my_starters)
    print_players('MY BENCH / IR', my_bench)
    print_players('OPPONENT STARTERS', opp_starters)
    print_players('OPPONENT BENCH', opp_bench)
    print()
    print('=' * 90)


def send_to_render(yahoo):
    url = os.getenv('FANTASY_DASHBOARD_URL', '').strip().rstrip('/')
    token = os.getenv('LEAGUESYNC_SYNC_TOKEN', '').strip()

    if not url or not token:
        print()
        print('Render upload skipped.')
        print('Set FANTASY_DASHBOARD_URL and LEAGUESYNC_SYNC_TOKEN in your local .env to enable it.')
        return False

    endpoint = url + '/api/yahoo-sync'
    print()
    print('Sending Yahoo data to Render...')

    response = requests.post(
        endpoint,
        json=yahoo,
        headers={'X-LeagueSync-Token': token},
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError('Render sync failed HTTP ' + str(response.status_code) + ': ' + response.text[:500])

    result = response.json()
    if not result.get('ok'):
        raise RuntimeError('Render sync was rejected: ' + str(result))

    print('Render Yahoo sync: SUCCESS')
    print('Dashboard URL: ' + url)
    return True


def main():
    driver = None
    try:
        driver = start_browser()
        data = get_dashboard_json(driver)
        yahoo = find_yahoo_league(data)
        save_results(data, yahoo)
        print_summary(yahoo)
        send_to_render(yahoo)
        print()
        print('Full data saved to: ' + str(FULL_OUTPUT))
        print('Yahoo data saved to: ' + str(YAHOO_OUTPUT))
        print()
        input('Press ENTER to close Firefox...')
    except Exception as exc:
        print()
        print('ERROR:')
        print(str(exc))
        input('Press ENTER to close Firefox...')
        sys.exit(1)
    finally:
        if driver is not None:
            driver.quit()


if __name__ == '__main__':
    main()
