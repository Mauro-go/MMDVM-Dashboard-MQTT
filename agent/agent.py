#!/usr/bin/env python3
"""MMDVM read-only source agent. Publishes telemetry; accepts no commands."""
import argparse
import configparser
import datetime
import json
import logging
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
import paho.mqtt.client as mqtt
import psutil

VERSION = '0.1.0'
UNITS = ['mmdvmhost', 'dmrgateway', 'ysfgateway', 'dstargateway', 'ircddbgateway', 'p25gateway', 'nxdngateway', 'm17gateway', 'aprsgateway']
FIELDS = {
    'General': ['Callsign', 'Id', 'Duplex', 'Timeout'],
    'Info': ['RXFrequency', 'TXFrequency', 'Power', 'Height'],
    'DMR': ['Enable', 'ColorCode', 'SelfOnly', 'EmbeddedLCOnly', 'DumpTAData'],
    'D-Star': ['Enable', 'Module', 'SelfOnly', 'AckReply'],
    'System Fusion': ['Enable', 'LowDeviation', 'SelfOnly'],
    'P25': ['Enable', 'NAC', 'SelfOnly'],
    'NXDN': ['Enable', 'RAN', 'SelfOnly'],
    'M17': ['Enable', 'CAN', 'SelfOnly'],
    'POCSAG': ['Enable', 'Frequency'],
    'FM': ['Enable', 'Callsign', 'CallsignSpeed', 'CallsignFrequency', 'CTCSSFrequency'],
    'DMR Network': ['Enable', 'Slot1', 'Slot2', 'Jitter'],
    'D-Star Network': ['Enable'], 'System Fusion Network': ['Enable'],
    'P25 Network': ['Enable'], 'NXDN Network': ['Enable'], 'M17 Network': ['Enable']}

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def load_settings(path):
    settings = json.loads(Path(path).read_text())
    if not settings.get('node_id') or any(x in settings['node_id'] for x in '/+#'):
        raise ValueError('Invalid node_id')
    prefix = settings['topic_prefix'].strip('/')
    if not prefix or any(x in prefix for x in '+#'):
        raise ValueError('Invalid topic_prefix')
    settings['topic_prefix'] = prefix
    settings['interval_seconds'] = max(5, int(settings.get('interval_seconds', 10)))
    broker = json.loads(Path(settings['broker_settings_file']).read_text())
    if not broker.get('host') or not 1 <= int(broker.get('port', 1883)) <= 65535:
        raise ValueError('Invalid broker settings')
    return settings, broker

def radio_config(settings):
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    with Path(settings['mmdvm_ini']).open(encoding='utf-8-sig') as stream:
        cfg.read_file(stream)
    selected = {section: {key: cfg.get(section, key) for key in keys if cfg.has_option(section, key)}
                for section, keys in FIELDS.items() if cfg.has_section(section)}
    modes = {section: cfg.getboolean(section, 'Enable', fallback=False)
             for section in ['D-Star', 'DMR', 'System Fusion', 'P25', 'NXDN', 'M17', 'POCSAG', 'FM']}
    return {'source': Path(settings['mmdvm_ini']).name, 'fields': selected, 'modes': modes,
            'policy': 'explicit_allowlist_no_credentials'}

def service_states():
    services = {}
    for unit in UNITS:
        try:
            result = subprocess.run(['/bin/systemctl', 'show', unit + '.service',
                '--property=LoadState', '--property=ActiveState', '--property=UnitFileState'],
                capture_output=True, text=True, timeout=3)
            values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            if values.get('LoadState') not in (None, 'not-found'):
                services[unit] = {'state': values.get('ActiveState', 'unknown'),
                                  'enabled': values.get('UnitFileState') == 'enabled'}
        except (OSError, subprocess.TimeoutExpired):
            services[unit] = {'state': 'unknown', 'enabled': None}
    return services

def telemetry():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    temperature = None
    try:
        temperature = next((v.current for group in psutil.sensors_temperatures().values() for v in group), None)
    except (OSError, AttributeError):
        pass
    return {'system': {'cpu_percent': psutil.cpu_percent(interval=None),
        'memory_percent': memory.percent, 'memory_total_bytes': memory.total,
        'memory_available_bytes': memory.available, 'disk_percent': disk.percent,
        'disk_total_bytes': disk.total, 'disk_free_bytes': disk.free,
        'temperature_c': temperature, 'uptime_seconds': int(time.time() - psutil.boot_time())},
        'services': service_states()}

def envelope(settings, values):
    return dict(schema_version=1, node_id=settings['node_id'], agent_version=VERSION,
                collected_at=stamp(), **values)

def make_client(settings, broker, suffix=''):
    client = mqtt.Client(client_id='mmdvm-agent-' + settings['node_id'] + suffix, clean_session=True)
    if broker.get('username'):
        client.username_pw_set(broker['username'], broker.get('password') or None)
    if broker.get('tls', False):
        client.tls_set()
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.max_queued_messages_set(20)
    return client

def run(settings, broker, dry_run=False):
    if dry_run:
        psutil.cpu_percent(interval=None)
        time.sleep(0.2)
        print(json.dumps(envelope(settings, {'config': radio_config(settings), **telemetry()}), indent=2))
        return
    stopped = threading.Event()
    connected = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    client = make_client(settings, broker)
    prefix = settings['topic_prefix']
    client.will_set(prefix + '/status', json.dumps({'schema_version': 1,
        'node_id': settings['node_id'], 'online': False, 'reason': 'connection_lost'}), qos=1, retain=True)
    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            connected.set()
            logging.info('Broker connected')
        else:
            logging.error('Broker rejected connection, code %s', rc)
    def on_disconnect(c, userdata, rc):
        connected.clear()
        if rc:
            logging.warning('Broker disconnected, code %s', rc)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    def publish(name, values):
        result = client.publish(prefix + '/' + name, json.dumps(envelope(settings, values)), qos=1, retain=True)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError('MQTT publish unavailable')
        deadline = time.monotonic() + 8
        while not result.is_published() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not result.is_published():
            raise RuntimeError('MQTT acknowledgement timeout')
    psutil.cpu_percent(interval=None)
    client.connect_async(broker['host'], int(broker.get('port', 1883)), keepalive=30)
    client.loop_start()
    logging.info('Agent started: node=%s, prefix=%s, interval=%ss', settings['node_id'], prefix, settings['interval_seconds'])
    try:
        while not stopped.is_set():
            if not connected.wait(timeout=1):
                continue
            try:
                values = telemetry()
                try:
                    config = radio_config(settings)
                    publish('config', config)
                    values['config_ok'] = True
                except (OSError, ValueError, configparser.Error) as exc:
                    values['config_ok'] = False
                    values['config_error'] = type(exc).__name__
                    logging.warning('Configuration read failed: %s', type(exc).__name__)
                publish('telemetry', dict(stale_after_seconds=max(30, settings['interval_seconds'] * 3), **values))
                publish('status', {'online': True, 'stale_after_seconds': max(30, settings['interval_seconds'] * 3)})
            except Exception as exc:
                logging.warning('Collection/publication failed: %s', type(exc).__name__)
            stopped.wait(settings['interval_seconds'])
    finally:
        if connected.is_set():
            try:
                publish('status', {'online': False, 'reason': 'service_stopped'})
            except Exception:
                pass
        client.disconnect()
        client.loop_stop()
        logging.info('Agent stopped')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/opt/mmdvm-agent/agent.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        settings, broker = load_settings(args.config)
        run(settings, broker, args.dry_run)
    except Exception as exc:
        logging.error('Agent failed: %s', type(exc).__name__)
        raise SystemExit(1)
