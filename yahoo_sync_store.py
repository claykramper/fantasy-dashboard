import os
import threading
import time

import requests


_latest_yahoo = None
_last_refresh = 0.0
_refresh_lock = threading.Lock()

CACHE_SECONDS = 300

LEAGUESYNC_URL = 'https://www.leaguesync.app/api/me/dashboard'

DEFAULT_REFERER = (
    'https://www.leaguesync.app/dashboard/'
    'bfe5618b-619a-443b-864c-17fdc8b7cfbb__0'
)


def set_latest_yahoo(data):
    global _latest_yahoo
    _latest_yahoo = data


def get_latest_yahoo():
    return _latest_yahoo


def refresh_yahoo(force=False):
    """
    Pull the latest Yahoo league data from LeagueSync.

    Returns the cached Yahoo data when possible.
    If a refresh fails but cached data exists, the cached data is retained.
    """

    global _latest_yahoo
    global _last_refresh

    session_cookie = os.getenv('LEAGUESYNC_SESSION_COOKIE')

    if not session_cookie:
        raise RuntimeError(
            'LEAGUESYNC_SESSION_COOKIE is not configured.'
        )

    now = time.monotonic()

    if (
        not force
        and _latest_yahoo is not None
        and now - _last_refresh < CACHE_SECONDS
    ):
        return _latest_yahoo

    with _refresh_lock:
        # Check again after acquiring the lock in case another request
        # refreshed the data while we were waiting.
        now = time.monotonic()

        if (
            not force
            and _latest_yahoo is not None
            and now - _last_refresh < CACHE_SECONDS
        ):
            return _latest_yahoo

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/152.0.0.0 Safari/537.36'
            ),
            'Accept': '*/*',
            'Referer': os.getenv(
                'LEAGUESYNC_DASHBOARD_URL',
                DEFAULT_REFERER
            ),
        }

        try:
            response = requests.get(
                LEAGUESYNC_URL,
                cookies={'fh_session': session_cookie},
                headers=headers,
                timeout=15,
            )

            response.raise_for_status()

            data = response.json()

        except requests.RequestException as e:
            if _latest_yahoo is not None:
                return _latest_yahoo

            raise RuntimeError(
                f'LeagueSync request failed: {type(e).__name__}'
            ) from e

        except ValueError as e:
            if _latest_yahoo is not None:
                return _latest_yahoo

            raise RuntimeError(
                'LeagueSync returned invalid JSON.'
            ) from e

        if not isinstance(data, list):
            if _latest_yahoo is not None:
                return _latest_yahoo

            raise RuntimeError(
                'LeagueSync returned an unexpected response format.'
            )

        yahoo_leagues = [
            league
            for league in data
            if (
                isinstance(league, dict)
                and str(league.get('platform', '')).lower() == 'yahoo'
            )
        ]

        if not yahoo_leagues:
            if _latest_yahoo is not None:
                return _latest_yahoo

            raise RuntimeError(
                'LeagueSync returned no Yahoo leagues.'
            )

        # We currently have one Yahoo league.
        # If additional Yahoo leagues are added later, this can be
        # expanded to select a specific league.
        yahoo_data = yahoo_leagues[0]

        if not isinstance(yahoo_data.get('roster'), list):
            if _latest_yahoo is not None:
                return _latest_yahoo

            raise RuntimeError(
                'LeagueSync Yahoo data is missing the roster.'
            )

        if not isinstance(yahoo_data.get('current_matchup'), dict):
            if _latest_yahoo is not None:
                return _latest_yahoo

            raise RuntimeError(
                'LeagueSync Yahoo data is missing the current matchup.'
            )

        _latest_yahoo = yahoo_data
        _last_refresh = time.monotonic()

        return _latest_yahoo