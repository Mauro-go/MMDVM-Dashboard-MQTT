"""Read-only remote-node view; collector is the only cache writer."""
import datetime
import json
import os
import tempfile
import time
from pathlib import Path
import config as dashboard_config
STATE = Path(__file__).resolve().parent.parent / 'data' / 'agent-state.json'
KINDS = ('config', 'telemetry', 'status')
MODES = {'dmr':'DMR', 'dstar':'D-Star', 'ysf':'System Fusion', 'fm':'FM', 'p25':'P25', 'nxdn':'NXDN', 'm17':'M17', 'pocsag':'POCSAG', 'ax25':'AX.25'}
def enabled():
    return dashboard_config.get('deployment', 'mode', 'local') == 'remote'
def prefix():
    return dashboard_config.get('deployment', 'agent_topic_prefix', '').strip('/')
def node_id():
    return dashboard_config.get('deployment', 'node_id', '')
def read_cache():
    try:
        value = json.loads(STATE.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}
def ingest(topic, payload):
    if not enabled() or not prefix() or not topic.startswith(prefix() + '/'):
        return False
    kind = topic[len(prefix()) + 1:]
    if kind not in KINDS:
        return True
    if len(payload) > 131072:
        raise ValueError('Agent payload too large')
    value = json.loads(payload)
    if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('node_id') != node_id():
        raise ValueError('Agent schema/node mismatch')
    if kind == 'status' and not isinstance(value.get('online'), bool):
        raise ValueError('Invalid status')
    if kind == 'telemetry' and (not isinstance(value.get('system'), dict) or not isinstance(value.get('services'), dict)):
        raise ValueError('Invalid telemetry')
    if kind == 'config' and (not isinstance(value.get('fields'), dict) or not isinstance(value.get('modes'), dict)):
        raise ValueError('Invalid configuration')
    cache = read_cache()
    cache[kind] = {'received_at': time.time(), 'payload': value}
    fd, name = tempfile.mkstemp(prefix='.agent-', dir=str(STATE.parent))
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(cache, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, STATE)
    finally:
        if os.path.exists(name): os.unlink(name)
    return True
def fresh(record):
    try:
        payload = record['payload']
        if payload.get('node_id') != node_id() or payload.get('schema_version') != 1: return False
        limit = min(120, max(15, float(payload.get('stale_after_seconds', 30))))
        received_age = time.time() - float(record['received_at'])
        sent = datetime.datetime.fromisoformat(payload['collected_at'].replace('Z', '+00:00'))
        age = datetime.datetime.now(datetime.timezone.utc).timestamp() - sent.timestamp()
        return 0 <= received_age <= limit and -5 <= age <= limit
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        return False
def snapshot():
    cache = read_cache()
    status = cache.get('status', {})
    telemetry = cache.get('telemetry', {})
    config = cache.get('config', {})
    online = status.get('payload', {}).get('online') is True and fresh(status) and fresh(telemetry)
    config_ok = online and telemetry.get('payload', {}).get('config_ok') is True and fresh(config)
    return {'online': online, 'config_ok': config_ok,
            'telemetry': telemetry.get('payload', {}) if online else {},
            'config': config.get('payload', {}) if config_ok else {},
            'last_seen': telemetry.get('payload', {}).get('collected_at')}
def metadata():
    data = snapshot()
    telemetry = data.get('telemetry', {})
    version = telemetry.get('agent_version')

    if not isinstance(version, str) or len(version) > 32:
        version = None

    return {
        'mode': 'remote',
        'node_id': node_id(),
        'online': data['online'],
        'config_ok': data['config_ok'],
        'last_seen': data['last_seen'],
        'agent_version': version,
        'state': 'online' if data['online'] else 'offline_or_stale'
    }
def number(value):
    return value if isinstance(value, (int,float)) and not isinstance(value, bool) else None
def system_info():
    source = snapshot()['telemetry'].get('system', {})
    names = {'cpu':'cpu_percent', 'memory':'memory_percent', 'disk':'disk_percent',
             'temperature':'temperature_c', 'uptime':'uptime_seconds'}
    return {key:number(source.get(field)) for key,field in names.items()}
def modes():
    source = snapshot()['config'].get('modes', {})
    return {key:source.get(section) is True for key,section in MODES.items()}
def repeater_info():
    fields = snapshot()['config'].get('fields', {})
    general = fields.get('General', {})
    info = fields.get('Info', {})
    return {'callsign':str(general.get('Callsign') or '').strip(),
            'location':dashboard_config.get('repeater','location'),
            'description':'', 'rx_frequency':str(info.get('RXFrequency','')),
            'tx_frequency':str(info.get('TXFrequency','')), 'power':str(info.get('Power',''))}
def repeater_settings():
    info = repeater_info()
    fields = snapshot()['config'].get('fields', {})
    from radio_info import normalize_radio

    result = {
        'callsign': info['callsign'],
    }

    result.update(normalize_radio(
        fields,
        snapshot()['config'].get('modes', {})
    ))

    return result
def services(candidates):
    source = snapshot()['telemetry'].get('services', {})
    result = []
    for unit,name in candidates:
        value = source.get(unit.removesuffix('.service'))
        if not isinstance(value,dict): continue
        state = value.get('state','unknown')
        if state not in ('active','inactive','failed','activating','deactivating','reloading','unknown'): state='unknown'
        result.append({'unit':unit,'name':name,'state':state,'active':state=='active',
                       'enabled':'enabled' if value.get('enabled') is True else 'disabled'})
    return result
