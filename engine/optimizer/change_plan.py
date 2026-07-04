import hashlib
import json
from datetime import datetime, timezone


PLAN_VERSION = "0.6.1"
SUPPORTED_ACTIONS = {"noop", "mark_candidate", "remove_shape", "update_shape", "add_shape"}
SAFE_ACTIONS = {"noop", "mark_candidate"}
RISK_LEVELS = {"none", "low", "medium", "high"}
STATUSES = {"proposed", "applied", "skipped", "dry_run"}


def make_shape_uid(shape: dict, index: int) -> str:
    payload = {
        "index": index,
        "type": shape.get("type"),
        "data": shape.get("data"),
        "color": shape.get("color"),
        "score": shape.get("score"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def make_optimization_plan(
    input_geometry_path: str,
    output_geometry_path: str | None,
    optimization_mode: str,
    shape_count_before: int,
    changes: list | None = None,
    warnings: list | None = None,
    safety_level: str = "safe",
) -> dict:
    changes = changes or []
    applied_count = sum(1 for change in changes if change.get("status") == "applied")
    return {
        "plan_version": PLAN_VERSION,
        "input_geometry_path": str(input_geometry_path),
        "output_geometry_path": str(output_geometry_path) if output_geometry_path else None,
        "optimization_mode": optimization_mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safety_level": safety_level,
        "shape_count_before": shape_count_before,
        "proposed_change_count": len(changes),
        "applied_change_count": applied_count,
        "changes": changes,
        "warnings": warnings or [],
    }


def make_change_entry(
    change_id: str,
    action: str,
    shape_index: int | None,
    shape: dict | None = None,
    reason: str = "",
    risk_level: str = "none",
    status: str = "proposed",
    before=None,
    after=None,
    rollback=None,
    metadata: dict | None = None,
) -> dict:
    shape_uid = make_shape_uid(shape, shape_index) if shape is not None and shape_index is not None else None
    return {
        "change_id": change_id,
        "action": action,
        "shape_index": shape_index,
        "shape_uid": shape_uid,
        "shape_type": shape.get("type") if isinstance(shape, dict) else None,
        "reason": reason,
        "risk_level": risk_level,
        "status": status,
        "before": before,
        "after": after,
        "rollback": rollback,
        "metadata": metadata or {},
    }
