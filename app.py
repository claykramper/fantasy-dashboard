import os

import requests
from flask import Flask, jsonify, render_template, request

from config import SECRET_KEY
from dashboard import build_dashboard
from yahoo import get_yahoo_access_token, get_yahoo_games, get_yahoo_leagues, yahoo_callback, yahoo_login
from yahoo_sync_store import set_latest_yahoo

app = Flask(__name__)
app.secret_key = SECRET_KEY


@app.route('/')
def index():
    return render_template('dashboard.html')


@app.route('/api/dashboard')
def api_dashboard():
    try:
        return jsonify(build_dashboard())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/yahoo-sync', methods=['POST'])
def yahoo_sync():
    expected_token = os.getenv('LEAGUESYNC_SYNC_TOKEN')
    supplied_token = request.headers.get('X-LeagueSync-Token')

    if not expected_token:
        return jsonify({'error': 'LEAGUESYNC_SYNC_TOKEN is not configured on the server.'}), 500

    if not supplied_token or supplied_token != expected_token:
        return jsonify({'error': 'Unauthorized.'}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected a Yahoo league JSON object.'}), 400

    if str(data.get('platform', '')).lower() != 'yahoo':
        return jsonify({'error': 'Posted data is not a Yahoo LeagueSync league.'}), 400

    roster = data.get('roster')
    matchup = data.get('current_matchup')
    if not isinstance(roster, list) or not isinstance(matchup, dict):
        return jsonify({'error': 'Yahoo data is missing roster or current_matchup.'}), 400

    set_latest_yahoo(data)

    starters = sum(
        1
        for p in roster
        if isinstance(p, dict) and p.get('status') == 'starter'
    )

    return jsonify({
        'ok': True,
        'team': data.get('team_name'),
        'starters': starters
    })


@app.route('/api/leaguesync-test')
def leaguesync_test():
    """
    Temporary diagnostic endpoint.

    Tests whether the Render server can use the LeagueSync
    fh_session cookie to retrieve the user's dashboard.
    """

    session_cookie = os.getenv('LEAGUESYNC_SESSION_COOKIE')

    if not session_cookie:
        return jsonify({
            'ok': False,
            'error': 'LEAGUESYNC_SESSION_COOKIE is not configured on Render.'
        }), 500

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/152.0.0.0 Safari/537.36'
        ),
        'Accept': '*/*',
        'Referer': 'https://www.leaguesync.app/dashboard/bfe5618b-619a-443b-864c-17fdc8b7cfbb__0',
    }

    try:
        response = requests.get(
            'https://www.leaguesync.app/api/me/dashboard',
            cookies={'fh_session': session_cookie},
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            return jsonify({
                'ok': False,
                'http_status': response.status_code,
                'error': 'LeagueSync did not accept the session from Render.'
            }), 502

        data = response.json()

        if not isinstance(data, list):
            return jsonify({
                'ok': False,
                'http_status': response.status_code,
                'error': 'LeagueSync returned an unexpected response format.'
            }), 502

        yahoo_leagues = [
            league
            for league in data
            if isinstance(league, dict)
            and str(league.get('platform', '')).lower() == 'yahoo'
        ]

        return jsonify({
            'ok': True,
            'http_status': response.status_code,
            'league_count': len(data),
            'yahoo_league_count': len(yahoo_leagues),
            'yahoo_teams': [
                league.get('team_name')
                for league in yahoo_leagues
                if league.get('team_name')
            ],
        })

    except requests.RequestException as e:
        return jsonify({
            'ok': False,
            'error': f'Request to LeagueSync failed: {type(e).__name__}'
        }), 502

    except ValueError:
        return jsonify({
            'ok': False,
            'http_status': response.status_code,
            'error': 'LeagueSync returned invalid JSON.'
        }), 502


@app.route('/yahoo/login')
def yahoo_login_route():
    return yahoo_login()


@app.route('/yahoo/callback')
def yahoo_callback_route():
    return yahoo_callback()


@app.route('/yahoo')
def yahoo_status():
    token = get_yahoo_access_token()
    games = None
    leagues = None
    games_error = None
    leagues_error = None

    if token:
        try:
            games = get_yahoo_games(token)
        except Exception as e:
            games_error = str(e)

        try:
            leagues = get_yahoo_leagues(token)
        except Exception as e:
            leagues_error = str(e)

    return render_template(
        'yahoo_status.html',
        connected=bool(token),
        games=games,
        leagues=leagues,
        games_error=games_error,
        leagues_error=leagues_error,
    )


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)