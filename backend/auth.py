"""Authentication primitives for the MMDVM Dashboard administration interface.

This module deliberately does not register public routes. Integrate it with a
protected Flask blueprint after configuring HTTPS, sessions and CSRF checks.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

STATE_DIR = Path(os.environ.get("MMDVM_DASHBOARD_STATE_DIR", "/var/lib/mmdvm-dashboard"))
CREDENTIALS_FILE = STATE_DIR / "admin.json"
SETUP_TOKEN_FILE = STATE_DIR / "setup-token"


class AuthError(ValueError):
    """An expected authentication or validation failure."""


def _validate_username(username: str) -> str:
    if not isinstance(username, str):
        raise AuthError("Invalid username")
    username = username.strip()
    if not (3 <= len(username) <= 64) or not all(
        c.isascii() and (c.isalnum() or c in "._-") for c in username
    ):
        raise AuthError("Username must be 3–64 characters: letters, digits, . _ -")
    return username


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or not (12 <= len(password) <= 1024):
        raise AuthError("Password must be between 12 and 1024 characters")


def _read_credentials() -> dict[str, Any] | None:
    try:
        with CREDENTIALS_FILE.open("r", encoding="utf-8") as handle:
            obj = json.load(handle)
    except FileNotFoundError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("username"), str) or not isinstance(obj.get("password_hash"), str):
        raise AuthError("Credential store is invalid")
    return obj


def is_configured() -> bool:
    return _read_credentials() is not None


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically replace a JSON file, owned by the service user and mode 0600."""
    fd, tmp_name = tempfile.mkstemp(prefix=".admin-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def verify_setup_token(candidate: str) -> bool:
    if is_configured() or not isinstance(candidate, str):
        return False
    try:
        expected = SETUP_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return False
    return bool(expected) and hmac.compare_digest(expected, candidate)


def create_initial_admin(setup_token: str, username: str, password: str) -> None:
    """Create the first administrator; never overwrite an existing account.

    The web integration must rate-limit this action and enforce HTTPS/CSRF.
    """
    username = _validate_username(username)
    _validate_password(password)
    if not verify_setup_token(setup_token):
        raise AuthError("Invalid setup token or administrator already configured")
    credentials = {"username": username, "password_hash": generate_password_hash(password)}

    # Exclusive creation prevents a second first-run request overwriting credentials.
    payload = (json.dumps(credentials, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        fd = os.open(str(CREDENTIALS_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AuthError("Administrator already configured") from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        CREDENTIALS_FILE.unlink(missing_ok=True)
        raise
    SETUP_TOKEN_FILE.unlink(missing_ok=True)


def verify_login(username: str, password: str) -> bool:
    if not isinstance(username, str) or not isinstance(password, str):
        return False
    credentials = _read_credentials()
    if not credentials:
        return False
    valid_user = hmac.compare_digest(credentials["username"], username)
    # Always check the hash to avoid a simple username-based timing difference.
    valid_password = check_password_hash(credentials["password_hash"], password)
    return valid_user and valid_password


def change_credentials(current_password: str, new_username: str, new_password: str | None = None) -> None:
    """Change account details after verifying the existing password.

    Call only from an authenticated, CSRF-protected administration endpoint.
    """
    credentials = _read_credentials()
    if not credentials or not isinstance(current_password, str) or not check_password_hash(
        credentials["password_hash"], current_password
    ):
        raise AuthError("Current password is incorrect")
    new_username = _validate_username(new_username)
    new_hash = credentials["password_hash"]
    if new_password is not None:
        _validate_password(new_password)
        new_hash = generate_password_hash(new_password)
    _atomic_write_json(CREDENTIALS_FILE, {"username": new_username, "password_hash": new_hash})


def generate_csrf_token() -> str:
    """Generate a token for the Flask session; comparison belongs in the route."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(expected: str | None, supplied: str | None) -> bool:
    return (
        isinstance(expected, str)
        and isinstance(supplied, str)
        and bool(expected)
        and hmac.compare_digest(expected, supplied)
    )
