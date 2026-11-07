#!/usr/bin/env python3
"""Controllo delle release ufficiali MMDVM Dashboard MQTT."""

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

APP_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = APP_ROOT / "VERSION"
RELEASE_URL = (
    "https://api.github.com/repos/"
    "Mauro-go/MMDVM-Dashboard-MQTT/releases/latest"
)

VERSION_PATTERN = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)$"
)


def parse_version(value):
    match = VERSION_PATTERN.fullmatch(str(value).strip())
    return tuple(map(int, match.groups())) if match else None


def installed_version():
    try:
        value = VERSION_FILE.read_text(encoding="utf-8").strip()
        return value or None
    except OSError:
        return None


def check_updates():
    installed = installed_version()

    result = {
        "installed": installed,
        "latest": None,
        "status": "unknown",
        "release_url": None,
        "release_notes": None,
        "error": None,
    }

    request = Request(
        RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MMDVM-Dashboard-MQTT",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            release = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            result["status"] = "no_releases"
        else:
            result["status"] = "error"
            result["error"] = f"GitHub HTTP {exc.code}"
        return result
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result

    latest = str(release.get("tag_name") or "").strip()
    result["latest"] = latest or None

    url = release.get("html_url")
    if isinstance(url, str) and url.startswith(
        "https://github.com/Mauro-go/MMDVM-Dashboard-MQTT/releases/"
    ):
        result["release_url"] = url

    result["release_notes"] = str(release.get("body") or "")[:12000]

    current_number = parse_version(installed) if installed else None
    latest_number = parse_version(latest)

    if not latest_number:
        result["status"] = "unknown"
    elif not current_number:
        result["status"] = "installed_unknown"
    elif latest_number > current_number:
        result["status"] = "update_available"
    else:
        result["status"] = "up_to_date"

    return result


if __name__ == "__main__":
    print(json.dumps(check_updates(), indent=2, ensure_ascii=False))
