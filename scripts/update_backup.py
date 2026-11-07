#!/usr/bin/env python3
"""Backup del codice applicativo per gli aggiornamenti."""

import hashlib
import json
import os
import shutil
from pathlib import Path

COMPONENTS = ("backend", "frontend", "admin", "VERSION")


def backup_application(source, destination):
    source = Path(source)
    destination = Path(destination)

    if source.is_symlink() or not source.is_dir():
        raise ValueError("Directory sorgente non valida")

    if destination.exists() or destination.is_symlink():
        raise ValueError("Destinazione già esistente")

    for component in COMPONENTS:
        item = source / component

        if item.is_symlink() or not item.exists():
            raise ValueError("Componente mancante o non sicuro: " + component)

        if component == "VERSION":
            if not item.is_file():
                raise ValueError("VERSION non è un file")
        elif not item.is_dir():
            raise ValueError("Directory applicativa non valida: " + component)

        if component != "VERSION":
            for root, dirs, files in os.walk(item, followlinks=False):
                for name in dirs + files:
                    entry = Path(root) / name
                    if entry.is_symlink():
                        raise ValueError(
                            "Collegamento simbolico non consentito: "
                            + str(entry)
                        )

    destination.mkdir(mode=0o700, parents=False)

    try:
        for component in COMPONENTS:
            src = source / component
            dst = destination / component

            if component == "VERSION":
                shutil.copy2(src, dst)
            else:
                shutil.copytree(src, dst, symlinks=False)

    except Exception:
        shutil.rmtree(destination)
        raise

    return destination


def restore_application(backup, destination, expected_manifest):
    """Ripristina il codice soltanto dopo la verifica di integrità.

    Da utilizzare soltanto con i servizi interessati arrestati.
    Il manifest deve provenire da una posizione protetta.
    """
    backup = Path(backup)
    destination = Path(destination)

    verify_backup(backup, expected_manifest)

    if backup.is_symlink() or not backup.is_dir():
        raise ValueError("Backup non valido")

    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Destinazione non valida")

    for component in COMPONENTS:
        source = backup / component

        if source.is_symlink() or not source.exists():
            raise ValueError("Componente mancante nel backup: " + component)

        if component == "VERSION":
            if not source.is_file():
                raise ValueError("VERSION non valida")
        elif not source.is_dir():
            raise ValueError("Directory non valida: " + component)

        if component != "VERSION":
            for root, dirs, files in os.walk(source, followlinks=False):
                for name in dirs + files:
                    if (Path(root) / name).is_symlink():
                        raise ValueError("Link simbolico nel backup")

    for component in COMPONENTS:
        target = destination / component
        source = backup / component

        if target.is_symlink():
            raise ValueError("Destinazione con link simbolico")

        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

        if component == "VERSION":
            shutil.copy2(source, target)
        else:
            shutil.copytree(source, target, symlinks=False)

    return destination



def backup_manifest(directory):
    """Calcola le impronte SHA-256 dei file applicativi."""
    directory = Path(directory)

    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Directory backup non valida")

    result = {}

    for component in COMPONENTS:
        target = directory / component

        if target.is_symlink() or not target.exists():
            raise ValueError("Componente backup non valido: " + component)

        if component == "VERSION":
            if not target.is_file():
                raise ValueError("VERSION non valida")
            paths = [target]
        else:
            if not target.is_dir():
                raise ValueError("Directory backup non valida")
            paths = []
            for root, dirs, files in os.walk(target, followlinks=False):
                for name in dirs + files:
                    entry = Path(root) / name
                    if entry.is_symlink():
                        raise ValueError("Link simbolico nel backup")
                paths.extend(Path(root) / name for name in files)

        for path in paths:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)

            result[path.relative_to(directory).as_posix()] = digest.hexdigest()

    return result


def verify_backup(directory, expected_manifest):
    """Confronta il backup con le impronte originali."""
    actual = backup_manifest(directory)

    if actual != expected_manifest:
        raise ValueError("Integrità del backup compromessa")

    return True



def save_backup_manifest(backup, manifest_path):
    """Salva il manifest senza sovrascrivere file esistenti."""
    backup = Path(backup)
    manifest_path = Path(manifest_path)

    manifest = backup_manifest(backup)

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)

    fd = os.open(manifest_path, flags, 0o600)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        manifest_path.unlink(missing_ok=True)
        raise

    return manifest_path


def load_backup_manifest(manifest_path):
    """Legge un manifest da un file regolare protetto."""
    manifest_path = Path(manifest_path)

    if manifest_path.is_symlink():
        raise ValueError("Manifest con link simbolico")

    info = manifest_path.stat()

    if not manifest_path.is_file():
        raise ValueError("Manifest non regolare")

    if info.st_mode & 0o077:
        raise ValueError("Permessi manifest troppo aperti")

    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)

    if not isinstance(manifest, dict):
        raise ValueError("Formato manifest non valido")

    return manifest



def verify_backup_directory(directory):
    """Verifica proprietà e permessi della directory di backup."""
    import stat

    directory = Path(directory)

    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Directory di backup non valida")

    info = directory.stat()

    if info.st_uid != 0:
        raise ValueError("La directory deve appartenere a root")

    if stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("La directory deve avere permessi 0700")

    return True
