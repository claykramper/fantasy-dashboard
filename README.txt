FANTASY DASHBOARD - LEAGUESYNC RENDER INTEGRATION

WHAT THIS VERSION DOES
1. Opens LeagueSync in a dedicated Firefox profile.
2. Uses the authenticated LeagueSync browser session to retrieve /api/me/dashboard.
3. Extracts the Yahoo league and saves local JSON files.
4. Sends the Yahoo league JSON securely to the Render dashboard.
5. Render keeps the latest Yahoo data in memory and serves it through /api/dashboard.

INSTALL LOCAL DEPENDENCY
Run from the fantasy-dashboard folder:
py -3.12 -m pip install selenium requests python-dotenv

RENDER SETUP
In Render, open your fantasy-dashboard service and add this environment variable:
LEAGUESYNC_SYNC_TOKEN

Generate a random token locally with:
py -3.12 -c "import secrets; print(secrets.token_urlsafe(32))"

Copy the generated value into the Render LEAGUESYNC_SYNC_TOKEN environment variable.

LOCAL .env SETUP
In your fantasy-dashboard folder, create or edit .env and add:
FANTASY_DASHBOARD_URL=https://fantasy-dashboard-fn64.onrender.com
LEAGUESYNC_SYNC_TOKEN=PASTE_THE_SAME_TOKEN_HERE

Do not commit .env to GitHub. It is already covered by .gitignore.

DEPLOY
Replace app.py, dashboard.py, yahoo_sync_store.py, and leaguesync_sync.py in your GitHub project with the files in this package, then commit and push.
Render should redeploy automatically.

TEST
After Render redeploys:
1. Run: py -3.12 leaguesync_sync.py
2. Log into LeagueSync if Firefox asks.
3. Press ENTER after the LeagueSync dashboard is visible.
4. Confirm the terminal says: Render Yahoo sync: SUCCESS
5. Open the Render dashboard.
6. Yahoo should now appear between Sleeper and ESPN.

IMPORTANT
The Yahoo projections supplied by LeagueSync are null, so this version does not invent projections. Finished/live/upcoming status and actual points are preserved.

The Render free service stores the latest Yahoo data in memory. If Render restarts, simply run the sync again. We can add persistent storage later if needed.
