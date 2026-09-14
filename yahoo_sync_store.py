_latest_yahoo = None


def set_latest_yahoo(data):
    global _latest_yahoo
    _latest_yahoo = data


def get_latest_yahoo():
    return _latest_yahoo
