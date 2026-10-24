"""Private Telegram notification settings for MMDVM Dashboard (Python 3.9+)."""
import json
import os
import tempfile
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent.parent / 'data' / 'telegram-settings.json'
MODES = ('DMR', 'D-Star', 'YSF', 'P25', 'NXDN', 'FM', 'M17')
DEFAULTS = {
    'enabled': False,
    'bot_token': '',
    'chat_id': '',
    'modes': ['DMR'],
    'tg_policy': 'all_except',
    'tg_include': [],
    'tg_exclude': [],
    'callsign_exclude': [],
    'exclude_time': True,
    'exclude_beacons': True,
    'min_duration': 2.0,
    'notification_gap': 10.0,
    'sources': ['rf', 'network'],
}


def load():
    if not SETTINGS.exists():
        return dict(DEFAULTS)
    with SETTINGS.open(encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('Invalid Telegram settings')
    return {**DEFAULTS, **data}


def public():
    data = load()
    data.pop('bot_token', None)
    data['bot_token_set'] = bool(load().get('bot_token'))
    return data


def _int_list(value, name):
    if not isinstance(value, list) or len(value) > 500:
        raise ValueError('Invalid ' + name)
    result = []
    for item in value:
        if isinstance(item, bool) or not str(item).isdigit():
            raise ValueError('Invalid ' + name)
        n = int(item)
        if not 1 <= n <= 16777215:
            raise ValueError('Invalid ' + name)
        if n not in result:
            result.append(n)
    return result


def _strings(value, name, allowed=None):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('Invalid ' + name)
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 32:
            raise ValueError('Invalid ' + name)
        item = item.strip().upper() if name == 'callsign_exclude' else item.strip()
        if any(ord(ch) < 33 for ch in item):
            raise ValueError('Invalid ' + name)
        if allowed is not None and item not in allowed:
            raise ValueError('Invalid ' + name)
        if item not in result:
            result.append(item)
    return result


def save(changes):
    if not isinstance(changes, dict):
        raise ValueError('Invalid Telegram settings')
    allowed = set(DEFAULTS) | {'clear_bot_token'}
    if set(changes) - allowed:
        raise ValueError('Unknown Telegram setting')
    data = load()
    for key in ('enabled', 'exclude_time', 'exclude_beacons'):
        if key in changes:
            if not isinstance(changes[key], bool):
                raise ValueError('Invalid ' + key)
            data[key] = changes[key]
    for key in ('min_duration', 'notification_gap'):
        if key in changes:
            value = changes[key]
            if isinstance(value, bool):
                raise ValueError('Invalid ' + key)
            try:
                value = float(value)
            except (ValueError, TypeError, OverflowError):
                raise ValueError('Invalid ' + key)
            if not 0 <= value <= 3600:
                raise ValueError('Invalid ' + key)
            data[key] = value
    if 'tg_policy' in changes:
        if changes['tg_policy'] not in ('all_except', 'only_included'):
            raise ValueError('Invalid TG policy')
        data['tg_policy'] = changes['tg_policy']
    for key in ('tg_include', 'tg_exclude'):
        if key in changes:
            data[key] = _int_list(changes[key], key)
    for key, allowed_values in (
        ('modes', MODES),
        ('sources', ('rf', 'network')),
        ('callsign_exclude', None),
    ):
        if key in changes:
            data[key] = _strings(changes[key], key, allowed_values)
    if 'chat_id' in changes:
        value = changes['chat_id']
        if not isinstance(value, str) or len(value) > 128 or any(ord(c) < 33 for c in value):
            raise ValueError('Invalid Telegram chat ID')
        data['chat_id'] = value
    if 'clear_bot_token' in changes and not isinstance(changes['clear_bot_token'], bool):
        raise ValueError('Invalid clear_bot_token')
    if changes.get('clear_bot_token'):
        data['bot_token'] = ''
    elif 'bot_token' in changes:
        value = changes['bot_token']
        if not isinstance(value, str) or len(value) > 256 or any(ord(c) < 33 for c in value):
            raise ValueError('Invalid Telegram token')
        if value:
            data['bot_token'] = value
    if data['enabled'] and (not data['bot_token'] or not data['chat_id']):
        raise ValueError('Telegram token and chat ID required when enabled')
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.telegram-', dir=str(SETTINGS.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, SETTINGS)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return public()
