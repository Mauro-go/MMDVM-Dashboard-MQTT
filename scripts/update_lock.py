#!/usr/bin/env python3
"""Blocco esclusivo per le operazioni di aggiornamento."""

import fcntl
import os
import stat
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def update_lock(path):
    """Acquisisce un blocco esclusivo senza attendere."""
    path = Path(path)

    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("Directory del lock non valida")

    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0)

    fd = os.open(path, flags, 0o600)

    try:
        info = os.fstat(fd)

        if not stat.S_ISREG(info.st_mode):
            raise ValueError("File lock non regolare")

        if info.st_uid != os.geteuid():
            raise ValueError("Proprietario lock non valido")

        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Permessi lock non validi")

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Aggiornamento già in corso")

        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)

    finally:
        os.close(fd)
