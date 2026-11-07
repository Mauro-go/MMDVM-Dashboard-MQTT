#!/usr/bin/env python3
"""Verifica release e destinazione prima dell'aggiornamento."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from update_deployment import get_profile

COMPONENTS = ("backend", "frontend", "admin", "VERSION")


def inspect_release(path):
    path = Path(path).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("La release non è una directory")

    result = {}
    for component in COMPONENTS:
        target = path / component
        valid = (
            target.is_file() if component == "VERSION"
            else target.is_dir()
        )
        result[component] = {
            "present": valid,
            "symlink": target.is_symlink(),
        }
    return result


def inspect_destination(path):
    path = Path(path).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Destinazione non valida")

    result = {}
    for component in COMPONENTS:
        target = path / component
        result[component] = {
            "exists": target.exists(),
            "symlink": target.is_symlink(),
        }

    for component in ("config", "data"):
        target = path / component
        result[component] = {
            "exists": target.exists(),
            "directory": target.is_dir(),
            "symlink": target.is_symlink(),
            "preserved": True,
        }

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("standard", "multi"), required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()

    profile = get_profile(args.mode)
    release = Path(args.release).resolve(strict=True)
    destination = Path(args.destination).resolve(strict=True)

    if release == destination:
        raise ValueError("Release e destinazione coincidono")

    if release in destination.parents or destination in release.parents:
        raise ValueError("Release e destinazione non possono essere annidate")

    report = {
        "mode": args.mode,
        "profile_directory": profile["directory"],
        "release": str(release),
        "destination": str(destination),
        "services": profile["services"],
        "release_components": inspect_release(release),
        "destination_components": inspect_destination(destination),
        "ready": False,
    }

    report["ready"] = all(
        item["present"] and not item["symlink"]
        for item in report["release_components"].values()
    ) and all(
        item["exists"] and not item["symlink"]
        for name, item in report["destination_components"].items()
        if name in COMPONENTS
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if not report["ready"]:
        raise SystemExit("Release o destinazione non idonea")

    print("\nVERIFICA FILE SUPERATA")
    print("Nessun servizio modificato")
    print("Nessun file installato")


if __name__ == "__main__":
    main()
