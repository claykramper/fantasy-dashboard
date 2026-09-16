import re
import unicodedata

from espn import build_espn_matchup, get_espn_projection_lookup
from nfl import (
    build_game_lookup,
    build_slate_data,
    get_next_slate_index,
    get_nfl_schedule,
)
from sleeper import build_sleeper_matchup
from yahoo_sync_store import refresh_yahoo


YAHOO_SCORING = {
    'pass_yd': 1 / 25,
    'pass_td': 6,
    'pass_int': -3,
    'pass_350_bonus': 4,
    'rush_yd': 1 / 10,
    'rush_td': 6,
    'rush_125_bonus': 3,
    'rush_150_bonus': 4,
    'rec': 1,
    'rec_yd': 1 / 10,
    'rec_td': 6,
    'rec_125_bonus': 2,
    'rec_150_bonus': 3,
    'return_td': 6,
    'two_pt': 2,
    'fumble_lost': -2,
    'off_fumble_return_td': 6,
    'fg_0_19': 3,
    'fg_20_29': 3,
    'fg_30_39': 3,
    'fg_40_49': 4,
    'fg_50_plus': 5,
    'xp_made': 1,
    'dst_sack': 3,
    'dst_int': 3,
    'dst_fumble_recovery': 3,
    'dst_td': 6,
    'dst_safety': 2,
    'dst_block_kick': 2,
    'dst_return_td': 6,
    'dst_pa_0': 15,
    'dst_pa_1_6': 12,
    'dst_pa_7_13': 8,
    'dst_pa_14_20': 3,
    'dst_pa_21_27': 0,
    'dst_pa_28_34': -3,
    'dst_pa_35_plus': -6,
    'dst_extra_point_return': 2,
}


def num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_name(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace('’', "'")
    text = re.sub(r"[^a-z0-9 ]", '', text)
    suffixes = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}
    return ' '.join(x for x in text.split() if x not in suffixes)


def position(player):
    value = str(player.get('position') or player.get('pos') or '').upper()
    if value in {'DEF', 'DST', 'D/ST', 'D'}:
        return 'D/ST'
    return value


def yahoo_projection_from_espn(stats, pos):
    """Convert ESPN's projected raw weekly categories to Yahoo scoring."""
    if not isinstance(stats, dict):
        return None

    def s(*keys):
        for key in keys:
            if str(key) in stats:
                return num(stats.get(str(key)))
        return 0.0

    if pos == 'QB':
        total = (
            s(3) * YAHOO_SCORING['pass_yd']
            + s(4) * YAHOO_SCORING['pass_td']
            + s(20) * YAHOO_SCORING['pass_int']
            + s(24) * YAHOO_SCORING['rush_yd']
            + s(25) * YAHOO_SCORING['rush_td']
            + s(26) * YAHOO_SCORING['two_pt']
            + s(53) * YAHOO_SCORING['rec']
            + s(42) * YAHOO_SCORING['rec_yd']
            + s(43) * YAHOO_SCORING['rec_td']
            + s(44) * YAHOO_SCORING['two_pt']
            + s(19) * YAHOO_SCORING['two_pt']
            + s(72) * YAHOO_SCORING['fumble_lost']
        )
        if s(3) >= 350:
            total += YAHOO_SCORING['pass_350_bonus']
        if s(24) >= 150:
            total += YAHOO_SCORING['rush_150_bonus']
        elif s(24) >= 125:
            total += YAHOO_SCORING['rush_125_bonus']
        if s(42) >= 150:
            total += YAHOO_SCORING['rec_150_bonus']
        elif s(42) >= 125:
            total += YAHOO_SCORING['rec_125_bonus']
        return round(total, 2)

    if pos in {'RB', 'WR', 'TE'}:
        rush = s(24)
        rec_yards = s(42)
        total = (
            rush * YAHOO_SCORING['rush_yd']
            + s(25) * YAHOO_SCORING['rush_td']
            + s(53) * YAHOO_SCORING['rec']
            + rec_yards * YAHOO_SCORING['rec_yd']
            + s(43) * YAHOO_SCORING['rec_td']
            + (s(101) + s(102)) * YAHOO_SCORING['return_td']
            + s(103) * YAHOO_SCORING['return_td']
            + s(72) * YAHOO_SCORING['fumble_lost']
            + (s(26) + s(44) + s(19)) * YAHOO_SCORING['two_pt']
        )
        if rush >= 150:
            total += YAHOO_SCORING['rush_150_bonus']
        elif rush >= 125:
            total += YAHOO_SCORING['rush_125_bonus']
        if rec_yards >= 150:
            total += YAHOO_SCORING['rec_150_bonus']
        elif rec_yards >= 125:
            total += YAHOO_SCORING['rec_125_bonus']
        return round(total, 2)

    if pos == 'K':
        return round(
            s(80) * YAHOO_SCORING['fg_0_19']
            + s(77) * YAHOO_SCORING['fg_40_49']
            + s(74) * YAHOO_SCORING['fg_50_plus']
            + s(86) * YAHOO_SCORING['xp_made'],
            2,
        )

    if pos == 'D/ST':
        # ESPN exposes points-allowed as bucket stats. This maps them to
        # the actual Yahoo buckets rather than using ESPN's fantasy total.
        pa_points = 0.0
        if s(89):
            pa_points += YAHOO_SCORING['dst_pa_0']
        elif s(90):
            pa_points += YAHOO_SCORING['dst_pa_1_6']
        elif s(91):
            pa_points += YAHOO_SCORING['dst_pa_7_13']
        elif s(121) or s(92):
            pa_points += YAHOO_SCORING['dst_pa_14_20']
        elif s(122):
            pa_points += YAHOO_SCORING['dst_pa_21_27']
        elif s(123):
            pa_points += YAHOO_SCORING['dst_pa_28_34']
        elif s(124) or s(125):
            pa_points += YAHOO_SCORING['dst_pa_35_plus']
        else:
            pa_points += YAHOO_SCORING['dst_pa_21_27']

        return round(
            s(99) * YAHOO_SCORING['dst_sack']
            + s(95) * YAHOO_SCORING['dst_int']
            + s(96) * YAHOO_SCORING['dst_fumble_recovery']
            + (s(93) + s(104) + s(103)) * YAHOO_SCORING['dst_td']
            + s(98) * YAHOO_SCORING['dst_safety']
            + s(97) * YAHOO_SCORING['dst_block_kick']
            + (s(101) + s(102)) * YAHOO_SCORING['dst_return_td']
            + pa_points,
            2,
        )

    return None


def is_flex_slot(slot):
    value = str(slot or '').upper().replace('-', '').replace(' ', '')
    return value in {'FLEX', 'W/R/T', 'WR/RB', 'RB/WR', 'W/T', 'WR/TE', 'RB/TE'} or 'FLEX' in value


def is_bench_slot(slot):
    return str(slot or '').upper() in {'BN', 'BENCH', 'IR', 'IL', 'RESERVE'}


def yahoo_player(player, lookup, espn_projection_lookup):
    team = str(player.get('team') or '').upper()
    game = lookup.get(team, {})
    raw_projection = player.get('projected_points')

    try:
        projected = float(raw_projection) if raw_projection is not None else None
    except (TypeError, ValueError):
        projected = None

    source = 'Yahoo' if projected is not None else None
    if projected is None:
        espn = espn_projection_lookup.get(normalize_name(player.get('name')))
        if espn:
            projected = yahoo_projection_from_espn(
                espn.get('stats'),
                position(player),
            )
            if projected is not None:
                source = 'ESPN → Yahoo'

    slot = player.get('slot') or player.get('roster_slot') or position(player)

    return {
        'name': player.get('name'),
        'position': position(player),
        'slot': slot,
        'actual': player.get('points'),
        'projected': projected,
        'projected_points': projected,
        'projection_source': source or 'Unavailable',
        'injury': player.get('injury_status'),
        'game_status': game.get('game_status', player.get('game_status', '')),
        'status_detail': game.get('status_detail', player.get('status_detail', '')),
        'status': player.get('status'),
        'nfl_team': game.get('team', player.get('team')),
        'opponent': game.get('opponent', player.get('opponent')),
        'game_time': game.get('game_time', player.get('game_time')),
        'pro_team_id': game.get('team_id'),
        'starter': False,
        'bench': True,
        'predicted_slot': 'BN',
    }


def predict_yahoo_lineup(players):
    """Preserve Yahoo's explicit FLEX slots, then fill RB/WR by projection."""
    for p in players:
        p['starter'] = False
        p['bench'] = True
        p['predicted_slot'] = 'BN'

    usable = [p for p in players if not is_bench_slot(p.get('slot'))]
    selected = set()

    def proj(p):
        return p.get('projected') if p.get('projected') is not None else -1

    # Yahoo explicitly tells us which roster entries are W/R/T/FLEX.
    explicit_flex = sorted(
        [p for p in usable if is_flex_slot(p.get('slot'))],
        key=proj,
        reverse=True,
    )[:3]

    for p in explicit_flex:
        p['starter'] = True
        p['bench'] = False
        p['predicted_slot'] = 'FLEX'
        selected.add(id(p))

    def take(position_name, count, slot_name):
        candidates = sorted(
            [p for p in usable if id(p) not in selected and p.get('position') == position_name],
            key=proj,
            reverse=True,
        )[:count]
        for p in candidates:
            p['starter'] = True
            p['bench'] = False
            p['predicted_slot'] = slot_name
            selected.add(id(p))

    take('QB', 1, 'QB')
    take('RB', 2, 'RB')
    take('WR', 2, 'WR')
    take('K', 1, 'K')
    take('D/ST', 1, 'D/ST')

    # If a fixed starter was explicitly provided and wasn't caught by the
    # position parser, retain it. Otherwise it remains bench.
    for p in usable:
        if id(p) in selected:
            continue
        if str(p.get('status') or '').lower() == 'starter' and not is_flex_slot(p.get('slot')):
            p['starter'] = True
            p['bench'] = False
            p['predicted_slot'] = p.get('slot') or p.get('position') or 'UTIL'
            selected.add(id(p))

    order = {'QB': 0, 'RB': 1, 'WR': 2, 'TE': 3, 'FLEX': 4, 'K': 5, 'D/ST': 6, 'BN': 7}
    players.sort(key=lambda p: (
        0 if p.get('starter') else 1,
        order.get(p.get('predicted_slot'), 8),
        -proj(p),
        str(p.get('name') or ''),
    ))
    return players


def yahoo_team(abbrev, team_name, players, lookup, espn_projection_lookup):
    converted = [yahoo_player(p, lookup, espn_projection_lookup) for p in players]
    predict_yahoo_lineup(converted)
    starters = [p for p in converted if p.get('starter')]
    actual_total = sum(num(p.get('actual')) for p in starters if p.get('actual') is not None)
    projected_total = sum(
        num(p.get('actual')) if p.get('actual') is not None and 'FINAL' in str(p.get('game_status') or '').upper()
        else num(p.get('projected'))
        for p in starters
    )
    return {
        'abbrev': abbrev,
        'team_name': team_name,
        'actual_total': actual_total,
        'projected_total': projected_total,
        'players': converted,
    }


def build_yahoo_matchup(data, lookup, espn_projection_lookup):
    if not data:
        return None
    matchup = data.get('current_matchup') or {}
    return {
        'league_name': data.get('league_name'),
        'week': matchup.get('week'),
        'my_team': yahoo_team(
            data.get('team_name') or 'Yahoo',
            data.get('team_name') or 'Yahoo',
            data.get('roster') or [],
            lookup,
            espn_projection_lookup,
        ),
        'opponent': yahoo_team(
            matchup.get('opponent') or 'Opponent',
            matchup.get('opponent') or 'Opponent',
            matchup.get('opponent_roster') or [],
            lookup,
            espn_projection_lookup,
        ),
        'actual_total': matchup.get('my_score'),
        'opponent_actual_total': matchup.get('opp_score'),
        'my_score': matchup.get('my_score'),
        'opp_score': matchup.get('opp_score'),
        'game_status': matchup.get('game_status'),
    }


def build_dashboard():
    nfl_games = get_nfl_schedule()
    slates, fantasy_week_key = build_slate_data(nfl_games)
    lookup = build_game_lookup(nfl_games)

    sleeper = None
    sleeper_error = None
    try:
        sleeper = build_sleeper_matchup(lookup)
    except Exception as e:
        sleeper_error = str(e)

    espn = None
    espn_error = None
    try:
        espn = build_espn_matchup(nfl_games)
    except Exception as e:
        espn_error = str(e)

    yahoo = None
    yahoo_error = None
    try:
        yahoo_data = refresh_yahoo()
        names = []
        for p in yahoo_data.get('roster') or []:
            names.append(p.get('name'))
        names.extend(
            p.get('name')
            for p in (yahoo_data.get('current_matchup') or {}).get('opponent_roster') or []
        )
        espn_projection_lookup = get_espn_projection_lookup(names)
        yahoo = build_yahoo_matchup(yahoo_data, lookup, espn_projection_lookup)
        if not yahoo:
            yahoo_error = 'Yahoo data could not be converted into a matchup.'
    except Exception as e:
        yahoo_error = str(e)

    return {
        'slates': slates,
        'fantasy_week_key': fantasy_week_key,
        'next_slate_id': get_next_slate_index(slates),
        'sleeper': sleeper,
        'sleeper_error': sleeper_error,
        'espn': espn,
        'espn_error': espn_error,
        'yahoo': yahoo,
        'yahoo_error': yahoo_error,
    }
