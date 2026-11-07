#!/usr/bin/env python3
"""Rileva il file di configurazione usato da MMDVMHost tramite systemd."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def run(*args):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def services():
    found = set()

    for command in (
        ("systemctl", "list-units", "--all", "--type=service",
         "--plain", "--no-legend", "--no-pager"),
        ("systemctl", "list-unit-files", "--type=service",
         "--no-legend", "--no-pager"),
    ):
        for line in run(*command).splitlines():
            parts = line.split()
            if not parts:
                continue

            name = parts[0]

            if not name.endswith(".service"):
                continue

            if re.search(r"(^|[-_])pc($|[-_.])", name, re.I):
                continue

            found.add(name)

    return sorted(
        found,
        key=lambda name: (
            "mmdvmhost" not in name.lower(),
            name.lower() != "mmdvmhost.service",
            name.lower(),
        ),
    )


def service_command(service):
    return run(
        "systemctl", "show", service,
        "--property=ExecStart",
        "--value",
        "--no-pager",
    ).strip()


def extract_args(command):
    if not command:
        return []

    if "argv[]=" in command:
        command = command.split("argv[]=", 1)[1]
        command = command.split(" ;", 1)[0]

    try:
        return shlex.split(command)
    except ValueError:
        return []


def valid_config(path):
    if not path or not path.startswith("/"):
        return False

    candidate = Path(path)

    if not candidate.is_file():
        return False

    if not os.access(candidate, os.R_OK):
        return False

    try:
        with candidate.open(
            "r", encoding="utf-8", errors="replace"
        ) as handle:
            sample = handle.read(16384)
    except OSError:
        return False

    return bool(
        re.search(r"(?m)^\s*\[General\]\s*$", sample)
        and re.search(
            r"(?mi)^\s*Callsign\s*=",
            sample,
        )
    )


def detect():
    for service in services():
        # Escludere sempre le istanze PC, anche nei test.
        if re.search(r"(^|[-_])pc($|[-_.])", service, re.I):
            continue

        command = service_command(service)
        args = extract_args(command)

        if not args:
            continue

        executable = " ".join(args[:3]).lower()
        service_name = service.lower()

        if (
            "mmdvmhost" not in executable
            and "mmdvm-host" not in executable
            and "mmdvmhost" not in service_name
        ):
            continue

        for argument in args[1:]:
            if valid_config(argument):
                return argument

    return None


if __name__ == "__main__":
    result = detect()

    if result:
        print(result)
    else:
        sys.exit(1)
