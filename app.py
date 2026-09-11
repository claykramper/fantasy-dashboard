from flask import Flask,jsonify,render_template
from config import SECRET_KEY
from dashboard import build_dashboard
from yahoo import get_yahoo_access_token,get_yahoo_games,get_yahoo_leagues,yahoo_callback,yahoo_login
app=Flask(__name__); app.secret_key=SECRET_KEY
@app.route('/')
def index(): return render_template('dashboard.html')
@app.route('/api/dashboard')
def api_dashboard():
    try:return jsonify(build_dashboard())
    except Exception as e:return jsonify({'error':str(e)}),500
@app.route('/yahoo/login')
def yahoo_login_route(): return yahoo_login()
@app.route('/yahoo/callback')
def yahoo_callback_route(): return yahoo_callback()
@app.route('/yahoo')
def yahoo_status():
    token=get_yahoo_access_token(); games=leagues=None; games_error=leagues_error=None
    if token:
        try: games=get_yahoo_games(token)
        except Exception as e: games_error=str(e)
        try: leagues=get_yahoo_leagues(token)
        except Exception as e: leagues_error=str(e)
    return render_template('yahoo_status.html',connected=bool(token),games=games,leagues=leagues,games_error=games_error,leagues_error=leagues_error)
if __name__=='__main__': app.run(host='127.0.0.1',port=5000,debug=False)
