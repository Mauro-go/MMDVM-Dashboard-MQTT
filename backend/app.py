#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import configparser
import psutil
import config as dashboard_config

from flask import Flask, jsonify, send_from_directory

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
from parser import load_live, get_repeater_callsign
from mqtt_sessions import reconstruct, dt
from datetime import datetime, timezone

app = Flask(__name__)

from admin_api import admin_bp, configure_admin_app
configure_admin_app(app)
app.register_blueprint(admin_bp)


def read_repeater_info():
    info = {
        "callsign": get_repeater_callsign() or "MMDVM",
        "location": "",
        "description": "",
        "rx_frequency": "",
        "tx_frequency": "",
        "power": "",
    }

    try:
        cfg = configparser.ConfigParser(strict=False)
        cfg.optionxform = str
        cfg.read(dashboard_config.get_mmdvm_ini())

        if cfg.has_section("Info"):
            info["location"] = cfg.get("Info", "Location", fallback="")
            info["description"] = cfg.get("Info", "Description", fallback="")
            info["rx_frequency"] = cfg.get("Info", "RXFrequency", fallback="")
            info["tx_frequency"] = cfg.get("Info", "TXFrequency", fallback="")
            info["power"] = cfg.get("Info", "Power", fallback="")
    except Exception:
        pass

    return info


def frequency_mhz(value):
    try:
        return "{:.4f}".format(int(value) / 1000000.0)
    except Exception:
        return ""


def system_info():
    try:
        temp = psutil.sensors_temperatures()
        cpu_temp = None

        for values in temp.values():
            if values:
                cpu_temp = values[0].current
                break
    except Exception:
        cpu_temp = None

    disk = psutil.disk_usage("/")

    return {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "memory": round(psutil.virtual_memory().percent, 1),
        "disk": round(disk.percent, 1),
        "temperature": cpu_temp,
        "uptime": int(time.time() - psutil.boot_time()),
    }


# Servizi radio/gateway supportati.
# Vengono mostrati solo quelli realmente installati sulla macchina.
SERVICE_CANDIDATES = [
    ("mmdvmhost.service",   "MMDVMHost"),
    ("dmrgateway.service",  "DMRGateway"),
    ("ysfgateway.service",  "YSFGateway"),
    ("dstargateway.service","DStarGateway"),
    ("ircddbgateway.service","ircDDBGateway"),
    ("p25gateway.service",  "P25Gateway"),
    ("nxdngateway.service", "NXDNGateway"),
    ("m17gateway.service",  "M17Gateway"),
    ("aprsgateway.service", "APRSGateway"),
]

def service_exists(unit):
    r = subprocess.run(
        ["systemctl", "show", unit, "--property=LoadState", "--value"],
        capture_output=True,
        text=True
    )

    return r.stdout.strip() not in ("", "not-found")


def service_state(unit):
    r = subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True,
        text=True
    )

    state = r.stdout.strip()

    return state if state else "unknown"


def service_enabled(unit):
    r = subprocess.run(
        ["systemctl", "is-enabled", unit],
        capture_output=True,
        text=True
    )

    return r.stdout.strip()


@app.route("/api/services")
def api_services():
    services = []

    for unit, name in SERVICE_CANDIDATES:
        if not service_exists(unit):
            continue

        state = service_state(unit)
        enabled = service_enabled(unit)

        services.append({
            "name": name,
            "unit": unit,
            "state": state,
            "enabled": enabled,
            "active": state == "active"
        })

    return jsonify(services)


def read_mmdvm_modes():
    """Legge le modalità abilitate direttamente da MMDVM.ini."""
    modes = {
        "dmr": False,
        "dstar": False,
        "ysf": False,
        "fm": False,
        "p25": False,
        "nxdn": False,
        "m17": False,
        "pocsag": False,
        "ax25": False,
    }

    sections = {
        "dmr": "DMR",
        "dstar": "D-Star",
        "ysf": "System Fusion",
        "fm": "FM",
        "p25": "P25",
        "nxdn": "NXDN",
        "m17": "M17",
        "pocsag": "POCSAG",
        "ax25": "AX.25",
    }

    cfg = configparser.ConfigParser(strict=False)
    cfg.read(dashboard_config.get_mmdvm_ini())

    for mode, section in sections.items():
        modes[mode] = cfg.getboolean(
            section, "Enable", fallback=False
        )

    return modes


@app.route("/api/config")
def api_config():
    return jsonify({
        "dashboard": {
            "language": dashboard_config.get("dashboard", "language"),
            "title": dashboard_config.get("dashboard", "title"),
        },
        "repeater": {
            "callsign": dashboard_config.get("repeater", "callsign"),
            "location": dashboard_config.get("repeater", "location"),
            "city": dashboard_config.get("repeater", "city"),
            "locator": dashboard_config.get("repeater", "locator"),
            "altitude": dashboard_config.get("repeater", "altitude"),
            "tx_frequency": dashboard_config.get("repeater", "tx_frequency"),
            "rx_frequency": dashboard_config.get("repeater", "rx_frequency"),
            "shift": dashboard_config.get("repeater", "shift"),
            "power": dashboard_config.get("repeater", "power"),
            "ctcss": dashboard_config.get("repeater", "ctcss"),
            "dmr_color_code": dashboard_config.get("repeater", "dmr_color_code"),
        },
        "modes": read_mmdvm_modes(),
        "station": {
            "organization": dashboard_config.get("station", "organization"),
            "organization_description": dashboard_config.get("station", "organization_description"),
            "maintainers": dashboard_config.get("station", "maintainers"),
            "collaboration": dashboard_config.get("station", "collaboration"),
        },
        "hardware": {
            "radio": dashboard_config.get("hardware", "radio"),
            "modem": dashboard_config.get("hardware", "modem"),
            "computer": dashboard_config.get("hardware", "computer"),
            "antenna": dashboard_config.get("hardware", "antenna"),
        },
        "images": {
            "banner": dashboard_config.get("images", "banner"),
            "repeater": dashboard_config.get("images", "repeater"),
            "logo": dashboard_config.get("images", "logo"),
        },
        "links": {
            "dstar_dashboard": dashboard_config.get("links", "dstar_dashboard"),
            "dstar_dashboard_label": dashboard_config.get("links", "dstar_dashboard_label"),
            "mmdvmhost_url": dashboard_config.get("links", "mmdvmhost_url"),
            "mmdvmhost_label": dashboard_config.get("links", "mmdvmhost_label"),
            "dmrgateway_url": dashboard_config.get("links", "dmrgateway_url"),
            "dmrgateway_label": dashboard_config.get("links", "dmrgateway_label"),
            "ysfgateway_url": dashboard_config.get("links", "ysfgateway_url"),
            "ysfgateway_label": dashboard_config.get("links", "ysfgateway_label"),
            "ircddbgateway_url": dashboard_config.get("links", "ircddbgateway_url"),
            "ircddbgateway_label": dashboard_config.get("links", "ircddbgateway_label"),
            "m17gateway_url": dashboard_config.get("links", "m17gateway_url"),
            "m17gateway_label": dashboard_config.get("links", "m17gateway_label"),
            "aprsgateway_url": dashboard_config.get("links", "aprsgateway_url"),
            "aprsgateway_label": dashboard_config.get("links", "aprsgateway_label"),
        },
    })


@app.route("/api/status")
def api_status():
    repeater = read_repeater_info()

    repeater["rx_frequency_mhz"] = frequency_mhz(
        repeater["rx_frequency"]
    )
    repeater["tx_frequency_mhz"] = frequency_mhz(
        repeater["tx_frequency"]
    )

    return jsonify({
        "repeater": repeater,
        "system": system_info(),
    })


@app.route("/api/heard")
def api_heard():
    history, active, fm = reconstruct()
    return jsonify(history)


@app.route("/api/live")
def api_live():
    history, active, fm = reconstruct()
    now = datetime.now(timezone.utc)
    timeout = 180

    candidates = []

    for (mode, slot), (started, payload) in active.items():
        start_dt = dt(started)
        if start_dt is None:
            continue

        elapsed = (now - start_dt).total_seconds()
        if elapsed < 0 or elapsed > timeout:
            continue

        direction = (
            "RF" if payload.get("source") == "rf"
            else "NET" if payload.get("source") == "network"
            else "?"
        )

        if mode == "DMR":
            callsign = str(payload.get("src_info") or "")
            source = str(payload.get("src_id") or "")
            destination = (
                ("TG " if payload.get("group") == "yes" else "")
                + str(payload.get("dst_id") or "")
            )
        else:
            callsign = str(payload.get("src_callsign") or "")
            source = callsign
            destination = str(
                payload.get("dst_callsign")
                or payload.get("reflector")
                or ""
            )

        candidates.append({
            "active": True,
            "mode": mode,
            "callsign": callsign,
            "source": source,
            "name": "",
            "destination": destination,
            "direction": direction,
            "slot": slot,
            "elapsed": round(elapsed, 1),
            "_started": start_dt,
        })

    if fm is not None:
        start_dt = dt(fm)
        if start_dt is not None:
            elapsed = (now - start_dt).total_seconds()
            if 0 <= elapsed <= timeout:
                candidates.append({
                    "active": True,
                    "mode": "FM",
                    "callsign": "",
                    "source": "FM",
                    "name": "",
                    "destination": "",
                    "direction": "RF",
                    "slot": None,
                    "elapsed": round(elapsed, 1),
                    "_started": start_dt,
                })

    if not candidates:
        return jsonify({"active": False})

    latest = max(candidates, key=lambda x: x["_started"])
    latest.pop("_started", None)
    return jsonify(latest)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def frontend(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get('MMDVM_DASHBOARD_PORT', '8089')),
        debug=False,
        threaded=True
    )
