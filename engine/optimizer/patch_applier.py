import copy

from engine.optimizer.change_plan import SAFE_ACTIONS


def apply_optimization_plan(
    geometry: dict,
    plan: dict,
    dry_run: bool = True,
    allow_destructive: bool = False,
) -> dict:
    modified_geometry = copy.deepcopy(geometry)
    ledger = []
    applied = 0
    dry_run_count = 0
    skipped = 0
    destructive = 0

    for change in plan.get("changes", []):
        action = change.get("action")
        entry = {
            "change_id": change.get("change_id"),
            "action": action,
            "shape_index": change.get("shape_index"),
            "shape_uid": change.get("shape_uid"),
            "dry_run": dry_run,
            "status": "skipped",
            "reason": "",
            "rollback": change.get("rollback"),
        }
        if action in SAFE_ACTIONS:
            entry["status"] = "dry_run" if dry_run else "applied"
            entry["reason"] = f"{action} does not modify geometry."
            if dry_run:
                dry_run_count += 1
            else:
                applied += 1
        elif action in {"remove_shape", "update_shape", "add_shape"}:
            destructive += 1
            if not allow_destructive:
                entry["reason"] = f"{action} is not implemented or allowed in v0.6.1."
                skipped += 1
            else:
                raise NotImplementedError(f"{action} is not implemented in v0.6.1.")
        else:
            entry["reason"] = f"Unsupported action: {action}"
            skipped += 1
        ledger.append(entry)

    return {
        "applied_change_count": applied,
        "dry_run_change_count": dry_run_count,
        "skipped_change_count": skipped,
        "destructive_change_count": destructive,
        "modified_geometry": modified_geometry,
        "ledger": ledger,
    }
