#!/usr/bin/env python3
"""Rileva il file INI utilizzato da MMDVMHost tramite systemd."""
import os
import shlex
import subprocess
import sys
from pathlib import Path


def detect():
    services = set()

    commands = [
        ["systemctl", "list-units", "--all", "--type=service",
         "--plain", "--no-legend", "--no-pager"],
        ["systemctl", "list-unit-files", "--type=service",
         "--no-legend", "--no-pager"],
    ]

    for command in commands:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True,
                timeout=10, check=True
            )
        except (OSError, subprocess.SubprocessError):
            continue

        for line in result.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue

            name = parts[0]
            lower = name.lower()

            if not lower.endswith(".service"):
                continue
            if "mmdvmhost" not in lower or "-pc" in lower:
                continue

            services.add(name)

    ordered = sorted(
        services,
        key=lambda x: (x.lower() != "mmdvmhost.service", x)
    )

    for service in ordered:
        try:
            result = subprocess.run(
                ["systemctl", "show", service, "--property=ExecStart",
                 "--value", "--no-pager"],
                capture_output=True, text=True, timeout=10, check=True
            )
        except (OSError, subprocess.SubprocessError):
            continue

        command = result.stdout.strip()
        if not command:
            continue

        if "argv[]=" in command:
            command = command.split("argv[]=", 1)[1]
            command = command.split(" ;", 1)[0]
        elif "path=" in command:
            command = command.split("path=", 1)[1]
            command = command.split(" ;", 1)[0]

        try:
            args = shlex.split(command)
        except ValueError:
            continue

        for arg in args:
            if not arg.startswith("/") or not arg.lower().endswith(".ini"):
                continue

            path = Path(arg)
            if path.is_file() and os.access(path, os.R_OK):
                return str(path)

    return None


if __name__ == "__main__":
    found = detect()
    if found:
        print(found)
    else:
        sys.exit(1)
