#!/usr/bin/env python3
"""Protected administration endpoints for MMDVM Dashboard.

Register with: app.register_blueprint(admin_bp)
Requires auth.py and a private state directory containing session-secret.
Compatible with Flask 1.1.x / Werkzeug 1.0.x.
"""

import hmac
import json
import os
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request, session, send_file

import auth

admin_bp = Blueprint("mmdvm_admin", __name__, url_prefix="/api/admin")
STATE_DIR = Path(os.environ.get("MMDVM_DASHBOARD_STATE_DIR", "/var/lib/mmdvm-dashboard"))
SECRET_FILE = STATE_DIR / "session-secret"
_LOCK = threading.Lock()
_ATTEMPTS = {}
_WINDOW_SECONDS = 900
_MAX_ATTEMPTS = 8


def configure_admin_app(app):
    """Call once before accepting requests, then register admin_bp."""
    secret = SECRET_FILE.read_text(encoding="ascii").strip()
    if len(secret) < 32:
        raise RuntimeError("Invalid admin session secret")
    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Strict",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    )


def _reply(message, status):
    return jsonify({"ok": False, "error": message}), status


def _json():
    if not request.is_json:
        return None
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _text(data, key):
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _same_origin():
    """Require an Origin or Referer matching the HTTPS site host."""
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return False
    parsed = urlsplit(origin)
    host = request.headers.get("Host", "")
    return parsed.scheme == "https" and parsed.netloc.lower() == host.lower()


def _limited(kind):
    # Shared limit is intentional: the reverse proxy may hide the real client IP.
    now = time.monotonic()
    with _LOCK:
        entries = [t for t in _ATTEMPTS.get(kind, []) if now - t < _WINDOW_SECONDS]
        if len(entries) >= _MAX_ATTEMPTS:
            _ATTEMPTS[kind] = entries
            return True
        entries.append(now)
        _ATTEMPTS[kind] = entries
        return False


def _reset_limit(kind):
    with _LOCK:
        _ATTEMPTS.pop(kind, None)


def _credentials_version():
    """Invalidate existing sessions when credentials change."""
    path = STATE_DIR / "admin.json"
    try:
        import hashlib
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _authenticated():
    version = _credentials_version()
    return bool(version and session.get("admin_authenticated") is True
                and hmac.compare_digest(str(session.get("credentials_version", "")), version))


def _require_auth():
    if not _authenticated():
        return _reply("Authentication required", 401)
    return None


def _require_csrf():
    expected = session.get("admin_csrf")
    supplied = request.headers.get("X-CSRF-Token")
    if not auth.verify_csrf_token(expected, supplied):
        return _reply("Invalid CSRF token", 403)
    return None


@admin_bp.after_request
def _no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@admin_bp.route("/", methods=["GET"])
def admin_page():
    """Serve the admin login and interface from a private directory."""
    return send_file(
        str(Path(__file__).resolve().parent.parent / "admin" / "admin.html"),
        mimetype="text/html"
    )


@admin_bp.route("/session", methods=["GET"])
def admin_session():
    configured = auth.is_configured()
    authenticated = _authenticated() if configured else False
    result = {"ok": True, "configured": configured, "authenticated": authenticated}
    if authenticated:
        if not session.get("admin_csrf"):
            session["admin_csrf"] = auth.generate_csrf_token()
        result["csrf_token"] = session["admin_csrf"]
    return jsonify(result)


@admin_bp.route("/setup", methods=["POST"])
def admin_setup():
    if not _same_origin():
        return _reply("Invalid request origin", 403)
    if auth.is_configured():
        return _reply("Administrator already configured", 409)
    if _limited("setup"):
        return _reply("Too many attempts; try again later", 429)
    data = _json()
    if data is None:
        return _reply("JSON body required", 400)
    try:
        auth.create_initial_admin(
            _text(data, "setup_token"), _text(data, "username"), _text(data, "password")
        )
    except (auth.AuthError, ValueError) as exc:
        return _reply(str(exc), 400)
    _reset_limit("setup")
    session.clear()
    return jsonify({"ok": True, "message": "Administrator created; please log in"}), 201


@admin_bp.route("/login", methods=["POST"])
def admin_login():
    if not _same_origin():
        return _reply("Invalid request origin", 403)
    if _limited("login"):
        return _reply("Too many attempts; try again later", 429)
    data = _json()
    if data is None:
        return _reply("JSON body required", 400)
    if not auth.verify_login(_text(data, "username"), _text(data, "password")):
        return _reply("Invalid username or password", 401)
    _reset_limit("login")
    session.clear()
    session.permanent = True
    session["admin_authenticated"] = True
    session["credentials_version"] = _credentials_version()
    session["admin_csrf"] = auth.generate_csrf_token()
    return jsonify({"ok": True, "csrf_token": session["admin_csrf"]})


@admin_bp.route("/logout", methods=["POST"])
def admin_logout():
    failure = _require_auth() or _require_csrf()
    if failure:
        return failure
    if not _same_origin():
        return _reply("Invalid request origin", 403)
    session.clear()
    return jsonify({"ok": True})


@admin_bp.route("/credentials", methods=["POST"])
def admin_credentials():
    failure = _require_auth() or _require_csrf()
    if failure:
        return failure
    if not _same_origin():
        return _reply("Invalid request origin", 403)
    if _limited("credentials"):
        return _reply("Too many attempts; try again later", 429)
    data = _json()
    if data is None:
        return _reply("JSON body required", 400)
    password = data.get("new_password")
    if password is not None and not isinstance(password, str):
        return _reply("Invalid password field", 400)
    try:
        auth.change_credentials(
            _text(data, "current_password"),
            _text(data, "new_username"),
            password,
        )
    except (auth.AuthError, ValueError) as exc:
        return _reply(str(exc), 400)
    _reset_limit("credentials")
    session.clear()
    return jsonify({"ok": True, "message": "Credentials updated; please log in again"})


@admin_bp.route("/mqtt", methods=["GET", "POST"])
def admin_mqtt():
    failure = _require_auth()
    if failure:
        return failure
    from mqtt_settings import public, save
    if request.method == "GET":
        try:
            return jsonify({"ok": True, "mqtt": public()})
        except Exception:
            current_app.logger.exception("MQTT settings read failed")
            return _reply("MQTT settings unavailable", 500)
    failure = _require_csrf()
    if failure:
        return failure
    if not _same_origin():
        return _reply("Invalid request origin", 403)
    if request.content_length is None or request.content_length > 4096:
        return _reply("Invalid request size", 413)
    data = _json()
    if data is None:
        return _reply("Invalid JSON data", 400)
    try:
        result = save(data)
    except ValueError as exc:
        return _reply(str(exc), 400)
    except Exception:
        current_app.logger.exception("MQTT settings save failed")
        return _reply("MQTT settings save failed", 500)
    return jsonify({"ok": True, "mqtt": result, "message": "MQTT settings saved"})


@admin_bp.route("/config", methods=["GET"])
def admin_read_config():
    """Restituisce i percorsi soltanto all'amministratore."""
    failure = _require_auth()
    if failure:
        return failure

    import config as dashboard_config

    keys = (
        "mmdvm_dir", "mmdvm_file", "mmdvm_logs",
        "dmr_ids", "tg_list_dir", "tg_list_file"
    )

    return jsonify({
        "paths": {
            key: dashboard_config.get_path(key)
            for key in keys
        }
    })


@admin_bp.route("/config", methods=["POST"])
def admin_save_config():
    """Salva esclusivamente le impostazioni della dashboard."""
    failure = _require_auth()
    if failure:
        return failure

    failure = _require_csrf()
    if failure:
        return failure

    if not _same_origin():
        return _reply("Invalid request origin", 403)

    if request.content_length is None or request.content_length > 16384:
        return _reply("Invalid request size", 413)

    data = _json()
    if data is None:
        return _reply("Invalid JSON data", 400)

    try:
        from config_writer import save_config
        import config as dashboard_config

        save_config(data)
        dashboard_config.reload_config()

    except ValueError as exc:
        return _reply(str(exc), 400)

    except Exception:
        current_app.logger.exception("Dashboard configuration save failed")
        return _reply("Configuration save failed", 500)

    return jsonify({"ok": True, "message": "Configuration saved"})
