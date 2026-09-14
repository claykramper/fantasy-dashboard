import os

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

    starters = sum(1 for p in roster if isinstance(p, dict) and p.get('status') == 'starter')
    return jsonify({'ok': True, 'team': data.get('team_name'), 'starters': starters})


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
