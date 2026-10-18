#!/usr/bin/env python3
"""Salvataggio sicuro della configurazione della dashboard."""

import fcntl
import os
import shutil
import tempfile
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

from config import CONFIG_FILE

ALLOWED = {
    "dashboard": {"language", "title"},
    "repeater": {
        "callsign", "location", "city", "locator", "altitude",
        "tx_frequency", "rx_frequency", "shift", "power",
        "ctcss", "dmr_color_code"
    },
    "station": {
        "organization", "organization_description",
        "maintainers", "collaboration"
    },
    "hardware": {"radio", "modem", "computer", "antenna"},
    "images": {"banner", "repeater", "logo"},
    "links": {'dstar_dashboard', 'dstar_dashboard_label', 'mmdvmhost_url', 'mmdvmhost_label', 'dmrgateway_url', 'dmrgateway_label', 'ysfgateway_url', 'ysfgateway_label', 'ircddbgateway_url', 'ircddbgateway_label', 'm17gateway_url', 'm17gateway_label', 'aprsgateway_url', 'aprsgateway_label'},
    "paths": {
        "mmdvm_dir", "mmdvm_file", "mmdvm_logs",
        "dmr_ids", "tg_list_dir", "tg_list_file"
    }
}


def save_config(changes):
    with CONFIG_FILE.with_name(".dashboard.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _save_config_locked(changes)


def _save_config_locked(changes):
    """Controlla e salva le impostazioni autorizzate."""
    if not isinstance(changes, dict) or not changes:
        raise ValueError("Configurazione non valida")

    cfg = ConfigParser(interpolation=None)
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg.read_file(f)

    for section, values in changes.items():
        if section not in ALLOWED or not isinstance(values, dict):
            raise ValueError("Sezione non autorizzata")

        if not cfg.has_section(section):
            raise ValueError("Sezione inesistente")

        for key, value in values.items():
            if key not in ALLOWED[section]:
                raise ValueError("Parametro non autorizzato")

            if not isinstance(value, str) or len(value) > 2048:
                raise ValueError("Valore non valido")

            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError("Caratteri non consentiti")

            cfg.set(section, key, value)

    if cfg.get("dashboard", "language", fallback="it") not in ("it", "en"):
        raise ValueError("Lingua non supportata")

    backup = CONFIG_FILE.with_name(
        CONFIG_FILE.name + ".bak-" +
        datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )

    temporary = None

    try:
        shutil.copy2(CONFIG_FILE, backup)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(CONFIG_FILE.parent),
            prefix=".dashboard-",
            suffix=".tmp",
            delete=False
        ) as f:
            temporary = Path(f.name)
            original = CONFIG_FILE.read_text(encoding="utf-8")
            f.write(update_ini_text(original, changes))
            f.flush()
            os.fsync(f.fileno())

        original_stat = CONFIG_FILE.stat()
        os.chown(temporary, -1, original_stat.st_gid)
        os.chmod(temporary, 0o660)
        os.replace(str(temporary), str(CONFIG_FILE))

    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

    return str(backup)


def update_ini_text(original, changes):
    """Aggiorna i valori INI conservando commenti e formattazione."""
    import re

    section = None
    updated = set()
    result = []

    for line in original.splitlines(keepends=True):
        match = re.match(r"^\s*\[([^\]]+)\]\s*(?:[#;].*)?$", line)

        if match:
            section = match.group(1).strip()

        elif section in changes:
            match = re.match(r"^(\s*)([^=:#\s]+)(\s*=\s*)(.*?)(\r?\n)?$", line)

            if match:
                key = match.group(2).lower()

                if key in changes[section]:
                    newline = (
                        "\r\n" if line.endswith("\r\n")
                        else "\n" if line.endswith("\n")
                        else ""
                    )
                    line = (
                        match.group(1) + match.group(2) +
                        match.group(3) + changes[section][key] + newline
                    )
                    updated.add((section, key))

        result.append(line)

    expected = {
        (section, key)
        for section, values in changes.items()
        for key in values
    }

    if updated != expected:
        raise ValueError("Parametri non trovati nel file INI")

    return "".join(result)
