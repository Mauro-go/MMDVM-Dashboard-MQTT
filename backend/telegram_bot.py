#!/usr/bin/env python3
"""MMDVM MQTT -> Telegram notifications. Python 3.9+."""
import configparser
import datetime as dt
import html
import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from mqtt_settings import load as mqtt_load
from telegram_settings import load as telegram_load

LOG = logging.getLogger('mmdvm-telegram')
from config import get_mmdvm_ini


def repeater_callsign():
    name = get_mmdvm_ini()
    cp = configparser.ConfigParser(interpolation=None, strict=False)

    try:
        with open(name, encoding='utf-8') as f:
            cp.read_file(f)
        call = cp.get('General', 'Callsign', fallback='').strip().upper()
        if call:
            return call
    except (OSError, configparser.Error) as exc:
        LOG.error('Cannot read configured MMDVM.ini at %s: %s', name, exc)

    raise RuntimeError(
        'Missing [General] Callsign in configured MMDVM.ini: ' + name
    )


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def event_time(event):
    value = event.get('timestamp')
    if isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is not None:
                return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            pass
    return utc_now()


def telegram_send(token, chat_id, message):
    payload = urllib.parse.urlencode({'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode()
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage', data=payload, method='POST')
    with urllib.request.urlopen(request, timeout=12) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram API returned failure')


class Bot:
    def __init__(self):
        self.mqtt = mqtt_load()
        self.callsign = repeater_callsign()
        self.starts = {}
        self.last_notification = 0.0
        self.client = None
        LOG.info('Repeater=%s; Telegram notifications active when enabled in Admin', self.callsign)

    def on_connect(self, client, userdata, flags, rc, *extra):
        if rc != 0:
            LOG.error('MQTT connection rejected: %s', rc)
            return
        self.starts.clear()
        topic = self.mqtt.get('topic') or 'mmdvm/+/json'
        client.subscribe(topic, qos=0)
        LOG.info('MQTT connected; subscribed=%s', topic)

    def on_disconnect(self, client, userdata, rc, *extra):
        self.starts.clear()
        LOG.warning('MQTT disconnected (%s)', rc)

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            if not isinstance(payload, dict):
                return
            # MMDVMHost MQTT: {"DMR": {...}} oppure {"D-Star": {...}}
            if isinstance(payload.get('DMR'), dict):
                mode = 'DMR'
                payload = payload['DMR']
            elif isinstance(payload.get('D-Star'), dict):
                mode = 'D-Star'
                payload = payload['D-Star']
            else:
                return
            action = str(payload.get('action', '')).lower()
            if action not in ('start', 'end'):
                return
            slot = str(payload.get('slot', '')) if mode == 'DMR' else ''
            key = (mode, slot)
            if action == 'start':
                self.starts[key] = (payload, time.monotonic(), event_time(payload))
            else:
                start = self.starts.pop(key, None)
                if not start:
                    LOG.info('SKIP %s end without matching start', mode)
                    return
                begin, tick, started_at = start
                if time.monotonic() - tick > 3600:
                    LOG.info('SKIP stale %s start', mode)
                    return
                self.process(mode, begin, payload, started_at)
        except Exception:
            LOG.exception('Failed to process MQTT message')

    def process(self, mode, begin, end, started_at):
        settings = telegram_load()  # reload each QSO so Admin changes apply without restart
        if not settings.get('enabled'):
            LOG.info('SKIP disabled')
            return
        if mode not in settings.get('modes', []):
            LOG.info('SKIP %s disabled mode', mode)
            return
        try:
            duration = float(end.get('duration', 0))
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= float(settings.get('min_duration', 2)):
            LOG.info('SKIP %s short duration %.2fs', mode, duration)
            return
        source = str(begin.get('source', '')).lower()
        if source not in settings.get('sources', ['rf', 'network']):
            LOG.info('SKIP %s source %s', mode, source)
            return
        if mode == 'DMR':
            caller = str(begin.get('src_info') or begin.get('src_id') or '').strip().upper()
            talkgroup = begin.get('dst_id')
            if not caller:
                LOG.info('SKIP DMR missing caller')
                return
            try:
                tg = int(talkgroup)
            except (ValueError, TypeError):
                LOG.info('SKIP DMR missing TG')
                return
            excluded = settings.get('tg_exclude', [])
            included = settings.get('tg_include', [])
            if tg in excluded or (settings.get('tg_policy') == 'only_included' and tg not in included):
                LOG.info('SKIP DMR TG filter: %s', tg)
                return
        else:
            caller = str(begin.get('src_callsign') or '').strip().upper()
            talkgroup = None
            ext = str(begin.get('src_ext') or '').strip().upper()
            if settings.get('exclude_time', True) and ext == 'TIME':
                LOG.info('SKIP D-Star time signal')
                return
            if settings.get('exclude_beacons', True) and caller == self.callsign:
                LOG.info('SKIP D-Star own repeater beacon')
                return
            if not caller:
                LOG.info('SKIP D-Star missing caller')
                return
        if caller in [x.upper() for x in settings.get('callsign_exclude', [])]:
            LOG.info('SKIP excluded callsign %s', caller)
            return
        gap = float(settings.get('notification_gap', 10))
        if time.monotonic() - self.last_notification < gap:
            LOG.info('SKIP rate limit')
            return
        title = '📡 ' + html.escape(self.callsign) + ' – Attività radio'
        fields = [f'<b>{title}</b>', f'Modo: <b>{html.escape(mode)}</b>', f'Nominativo: <b>{html.escape(caller)}</b>']
        if mode == 'DMR':
            fields.extend([f'DMR ID: {html.escape(str(begin.get("src_id", "")))}', f'TG: <b>{talkgroup}</b>', f'TS: {html.escape(str(begin.get("slot", "")))}'])
        else:
            fields.append('Reflector: ' + html.escape(str(begin.get('reflector', ''))))
        fields.extend([f'Origine: {html.escape(source)}', f'Durata: {duration:.1f} s', 'UTC: ' + started_at.strftime('%Y-%m-%d %H:%M:%S')])
        message = '\n'.join(fields)
        token = settings.get('bot_token', '')
        chat_id = settings.get('chat_id', '')
        if not token or not chat_id:
            LOG.warning('SKIP Telegram token/chat missing')
            return
        try:
            telegram_send(token, chat_id, message)
            self.last_notification = time.monotonic()
            LOG.info('SENT %s %s', mode, caller)
        except (urllib.error.URLError, ValueError, RuntimeError) as exc:
            LOG.error('Telegram send failed: %s', type(exc).__name__)

    def run(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError('Missing dependency: python3-paho-mqtt') from exc
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        except (AttributeError, TypeError):
            client = mqtt.Client()
        self.client = client
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message
        username = self.mqtt.get('username')
        if username:
            client.username_pw_set(username, self.mqtt.get('password') or None)
        if self.mqtt.get('tls'):
            client.tls_set()
        client.connect(str(self.mqtt['host']), int(self.mqtt['port']), keepalive=60)
        client.loop_forever(retry_first_connection=True)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    Bot().run()


if __name__ == '__main__':
    main()
