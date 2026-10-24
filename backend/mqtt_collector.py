#!/usr/bin/env python3
"""Dashboard-only MQTT collector; reconnects when private settings change.

SQLite events are retained for 48 hours. Cleanup runs at startup and once
per local calendar day after midnight, within the existing collector process.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from mqtt_store import connect, save
from mqtt_settings import SETTINGS, load

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mqtt-collector")

RETENTION_HOURS = 48
CLEANUP_CHECK_INTERVAL = 60  # seconds; no additional service or timer


def cleanup_old_events(db):
    """Remove expired events without deleting the database or WAL files.

    SQLite datetime() interprets ISO-8601 timestamps with UTC offsets and
    fractional seconds, and compares them to the current UTC time.
    """
    before = db.total_changes
    db.execute(
        "DELETE FROM events WHERE datetime(timestamp) < datetime('now', ?)",
        (f"-{RETENTION_HOURS} hours",),
    )
    db.commit()
    removed = db.total_changes - before
    # PASSIVE does not wait for dashboard readers and is safe in WAL mode.
    db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    logger.info("SQLite cleanup completed: removed %d events older than %d hours", removed, RETENTION_HOURS)


def on_message(client, userdata, msg):
    try:
        event = json.loads(msg.payload.decode("utf-8"))
        if not isinstance(event, dict):
            return
        for mode, payload in event.items():
            if not isinstance(payload, dict):
                continue
            timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
            action = payload.get("action") or payload.get("state") or ""
            save(userdata["db"], str(timestamp), str(mode), str(action), payload)
            logger.info("%s %s %s", mode, action, timestamp)
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        logger.warning("Invalid MQTT JSON: %s", exc)
    except Exception:
        logger.exception("Failed to store MQTT event")


def main():
    db = connect()
    client = None
    current = None
    retry_at = 0
    last_cleanup_date = None
    next_cleanup_check = 0.0
    try:
        while True:
            now = time.monotonic()
            if now >= next_cleanup_check:
                next_cleanup_check = now + CLEANUP_CHECK_INTERVAL
                today = datetime.now().date()  # local date, midnight rollover
                if today != last_cleanup_date:
                    try:
                        cleanup_old_events(db)
                        last_cleanup_date = today
                    except Exception:
                        logger.exception("SQLite cleanup failed; will retry")
                        try:
                            db.rollback()
                        except Exception:
                            pass
            try:
                settings = load()
                if not SETTINGS.exists():
                    settings.update({
                        "host": os.environ.get("MMDVM_MQTT_HOST", "127.0.0.1"),
                        "port": int(os.environ.get("MMDVM_MQTT_PORT", "1883")),
                        "topic": os.environ.get("MMDVM_MQTT_TOPIC", "mmdvm/+/json")
                    })
                signature = json.dumps(settings, sort_keys=True)
            except Exception:
                logger.exception("Invalid MQTT configuration; keeping current connection")
                time.sleep(3)
                continue
            if signature != current and time.monotonic() >= retry_at:
                if client is not None:
                    try:
                        client.disconnect()
                    except Exception:
                        pass
                    client = None
                try:
                    new_client = mqtt.Client(userdata={"db": db})
                    new_client.on_message = on_message
                    def connected(c, userdata, flags, rc):
                        if rc == 0:
                            c.subscribe(settings["topic"], qos=0)
                            logger.info("Subscribed: %s", settings["topic"])
                        else:
                            logger.error("MQTT connect error: %s", rc)
                    new_client.on_connect = connected
                    if settings.get("username"):
                        new_client.username_pw_set(settings["username"], settings.get("password") or None)
                    if settings.get("tls"):
                        new_client.tls_set()
                    new_client.connect(settings["host"], int(settings["port"]), keepalive=60)
                    client = new_client
                    current = signature
                    logger.info("MQTT connection configured")
                except Exception as exc:
                    logger.error("MQTT connection failed: %s", exc)
                    retry_at = time.monotonic() + 5
            if client is not None:
                try:
                    rc = client.loop(timeout=1.0)
                    if rc != mqtt.MQTT_ERR_SUCCESS:
                        client.reconnect()
                except Exception as exc:
                    logger.warning("MQTT reconnect pending: %s", exc)
                    time.sleep(3)
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopped")
    finally:
        if client is not None:
            client.disconnect()
        db.close()


if __name__ == "__main__":
    main()
