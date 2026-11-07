#!/usr/bin/env python3
"""Coordinatore sperimentale di aggiornamenti locali.

Non gestisce servizi systemd e non è autorizzato per produzione.
"""

import os
import uuid
from pathlib import Path

from update_backup import (
    backup_application,
    backup_manifest,
    restore_application,
    save_backup_manifest,
    verify_backup,
)
from update_journal import save_journal, load_journal
from update_lock import update_lock
from update_paths import transaction_paths
from update_deployment import get_profile
from update_atomic import replace_component, check_update_residues
from update_rename_plan import create_rename_plan, save_rename_plan
from update_tracked_swap import tracked_swap
from update_recovery import inspect_transaction_recovery

COMPONENTS = ("backend", "frontend", "admin", "VERSION")





def check_previous_transactions(backup_root):
    """Blocca nuove operazioni finché esistono transazioni irrisolte."""
    backup_root = Path(backup_root)

    for directory in sorted(backup_root.iterdir()):
        if directory.is_symlink():
            raise RuntimeError(
                "Transazione con collegamento simbolico"
            )

        if not directory.is_dir():
            continue

        journal_path = directory / "journal.json"

        if not journal_path.is_file() or journal_path.is_symlink():
            raise RuntimeError(
                "Transazione priva di journal valido: " + directory.name
            )

        journal = load_journal(journal_path)

        if journal["state"] in {"completed", "rolled_back"}:
            if journal.get("pending_component") is not None:
                raise RuntimeError(
                    "Transazione conclusa con operazione pendente"
                )
            continue

        transaction_id = directory.name

        try:
            result = inspect_transaction_recovery(
                backup_root,
                transaction_id,
            )
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            raise RuntimeError(
                "Aggiornamenti bloccati: transazione "
                + transaction_id
                + " non verificabile; intervento manuale richiesto"
            ) from exc

        if result.get("recovery_required") and result.get("backup_verified"):
            raise RuntimeError(
                "Aggiornamenti bloccati: recupero richiesto per "
                + transaction_id
                + " (stato: " + result["state"] + ")"
            )

        raise RuntimeError(
            "Aggiornamenti bloccati: transazione non conclusa "
            + transaction_id
        )


def run_simulated_update(
    application,
    release,
    backup_root,
    *,
    fail_after=None,
    tracked=False,
    mode="standard",
    production=False,
):
    """Aggiorna una copia di prova, con rollback sugli errori Python.

    Non garantisce recupero automatico dopo SIGKILL o blackout.
    """
    # Valida il profilo, senza modificare servizi o percorsi.
    profile = get_profile(mode)

    application = Path(application).resolve(strict=True)
    release = Path(release).resolve(strict=True)
    backup_root = Path(backup_root).resolve(strict=True)

    if production:
        expected = Path(profile["directory"]).resolve()

        if application != expected:
            raise ValueError(
                f"Percorso non autorizzato per {mode}: {application}"
            )

        raise RuntimeError(
            "Aggiornamenti di produzione non ancora abilitati"
        )

    if not application.is_dir() or not release.is_dir():
        raise ValueError("Directory applicazione/release non valida")

    if application == release:
        raise ValueError("Sorgente e destinazione coincidono")

    if (
        application in backup_root.parents
        or backup_root in application.parents
        or release in application.parents
        or application in release.parents
    ):
        raise ValueError("Percorsi sovrapposti")

    transaction_id = uuid.uuid4().hex
    paths = transaction_paths(backup_root, transaction_id)

    with update_lock(backup_root / "update.lock"):
        check_previous_transactions(backup_root)
        check_update_residues(application)
        paths["transaction"].mkdir(mode=0o700)

        # Un errore prima della prima modifica non richiede rollback.
        backup_application(application, paths["backup"])
        os.chmod(paths["backup"], 0o700)

        save_backup_manifest(
            paths["backup"],
            paths["manifest"],
        )

        manifest = backup_manifest(paths["backup"])
        verify_backup(paths["backup"], manifest)

        rename_plan = None
        rename_plan_path = paths["transaction"] / "rename-plan.json"

        if tracked:
            rename_plan = create_rename_plan(transaction_id)
            save_rename_plan(rename_plan_path, rename_plan)

        journal = {
            "transaction_id": transaction_id,
            "installation_path": str(application),
            "state": "prepared",
            "completed_components": [],
            "pending_component": None,
        }
        save_journal(paths["journal"], journal)

        try:
            journal["state"] = "installing"
            save_journal(paths["journal"], journal)

            for component in COMPONENTS:
                journal["pending_component"] = component
                save_journal(paths["journal"], journal)

                if tracked:
                    tracked_swap(
                        release,
                        application,
                        component,
                        rename_plan,
                        rename_plan_path,
                    )
                else:
                    replace_component(release, application, component)

                journal["completed_components"].append(component)
                journal["pending_component"] = None
                save_journal(paths["journal"], journal)

                if fail_after == component:
                    raise RuntimeError(
                        "Errore simulato dopo " + component
                    )

            journal["state"] = "completed"
            save_journal(paths["journal"], journal)

            return {
                "status": "completed",
                "transaction_id": transaction_id,
            }

        except Exception:
            journal["state"] = "rolling_back"
            save_journal(paths["journal"], journal)

            try:
                restore_application(
                    paths["backup"],
                    application,
                    manifest,
                )
            except Exception as rollback_error:
                raise RuntimeError(
                    "Aggiornamento fallito e rollback non riuscito; "
                    "recupero manuale necessario"
                ) from rollback_error

            journal["state"] = "rolled_back"
            journal["pending_component"] = None
            save_journal(paths["journal"], journal)
            raise


if __name__ == "__main__":
    print("Modulo sperimentale: eseguire i test dedicati.")
