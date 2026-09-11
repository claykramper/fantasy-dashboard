YAHOO_ROSTER = [
    {"name": "Player Name", "position": "QB"},
    {"name": "Player Name", "position": "RB"},
    {"name": "Player Name", "position": "WR"},
    {"name": "Player Name", "position": "TE"},
    ...
]

YAHOO_ROSTER_RULES = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 0,
    "FLEX": 3,
    "K": 1,
    "DST": 1,
    "FLEX_POSITIONS": ["RB", "WR", "TE"],
    "CLOSE_PROJECTION_THRESHOLD": 1.5,
}