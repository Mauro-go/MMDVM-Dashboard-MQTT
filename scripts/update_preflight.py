#!/usr/bin/env python3
"""Verifica installazioni Standard/Multi prima di un aggiornamento."""

import json
import subprocess
from pathlib import Path

from update_deployment import get_profile

COMPONENTS = ("backend", "frontend", "admin", "VERSION")
PERSISTENT = ("config", "data")


def systemctl_show(service):
    result = subprocess.run(
        [
            "systemctl", "show", service,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=FragmentPath",
            "--property=ExecStart",
            "--property=WorkingDirectory",
            "--property=EnvironmentFiles",
            "--no-pager",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode:
        return {"error": result.stderr.strip()}

    values = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def inspect(mode):
    profile = get_profile(mode)
    directory = Path(profile["directory"])

    candidates = [directory]

    if mode == "multi":
        candidates.append(
            Path("/opt/MMDVM-Dashboard-MQTT-Multi")
        )

    existing = [p for p in candidates if p.is_dir()]

    if existing:
        detected = existing[0]
    else:
        detected = directory

    result = {
        "detected_directory": str(detected),
        "mode": mode,
        "configured_directory": str(directory),
        "directory_exists": directory.is_dir(),
        "components": {},
        "persistent": {},
        "services": {},
        "warnings": [],
    }

    for name in COMPONENTS:
        path = detected / name
        result["components"][name] = path.exists()

    for name in PERSISTENT:
        path = detected / name
        result["persistent"][name] = {
            "exists": path.exists(),
            "directory": path.is_dir(),
            "symlink": path.is_symlink(),
        }

    for service in profile["services"]:
        info = systemctl_show(service)
        result["services"][service] = info

        if info.get("LoadState") != "loaded":
            result["warnings"].append(
                f"Servizio non caricato: {service}"
            )

        exec_start = info.get("ExecStart", "")
        working_dir = info.get("WorkingDirectory", "")

        if working_dir:
            result["services"][service]["DetectedWorkingDirectory"] = (
                working_dir
            )
        if (
            exec_start
            and str(detected) not in exec_start
            and str(detected) not in working_dir
        ):
            result["warnings"].append(
                f"Verificare ExecStart di {service}: "
                "non contiene la directory del profilo"
            )

    if not detected.is_dir():
        result["warnings"].append(
            "Directory del profilo inesistente"
        )

    missing = [
        name for name, present in result["components"].items()
        if not present
    ]
    if missing:
        result["warnings"].append(
            "Componenti mancanti: " + ", ".join(missing)
        )

    return result


def main():
    report = {
        "standard": inspect("standard"),
        "multi": inspect("multi"),
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n===== RIEPILOGO =====")
    for mode, data in report.items():
        print(
            f"{mode.upper()}: "
            f"{len(data['warnings'])} avvisi"
        )
        for warning in data["warnings"]:
            print(" -", warning)


if __name__ == "__main__":
    main()
