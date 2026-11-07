#!/usr/bin/env python3
"""Diagnostica non distruttiva di sostituzioni interrotte."""

from pathlib import Path

from update_rename_plan import (
    COMPONENTS,
    load_rename_plan,
    validate_rename_plan,
)


def inspect_swap_recovery(application, plan_path):
    """Determina quali componenti richiedono recupero o verifica."""
    application = Path(application)

    if application.is_symlink() or not application.is_dir():
        raise ValueError("Directory applicativa non valida")

    plan = load_rename_plan(plan_path)
    validate_rename_plan(plan)

    result = {}

    for component in COMPONENTS:
        operation = plan["operations"][component]

        target = application / operation["target"]
        prepared = application / operation["prepared"]
        previous = application / operation["previous"]

        paths = (target, prepared, previous)

        if any(path.is_symlink() for path in paths):
            classification = "unsafe_symlink"

        else:
            has_target = target.exists()
            has_prepared = prepared.exists()
            has_previous = previous.exists()

            if has_previous and not has_target:
                classification = "old_moved_target_missing"
            elif has_previous and has_target:
                classification = "old_and_new_present"
            elif has_prepared and has_target:
                classification = "prepared_with_target"
            elif has_prepared and not has_target:
                classification = "prepared_target_missing"
            elif has_target:
                classification = "target_only"
            else:
                classification = "all_missing"

        result[component] = {
            "journal_state": operation["state"],
            "classification": classification,
            "requires_review": (
                classification != "target_only"
                or operation["state"] not in ("planned", "done")
            ),
        }

    return {
        "transaction_id": plan["transaction_id"],
        "components": result,
        "requires_review": any(
            item["requires_review"]
            for item in result.values()
        ),
    }
