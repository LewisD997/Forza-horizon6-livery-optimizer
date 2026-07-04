import json
from pathlib import Path

from engine.optimizer.change_plan import (
    RISK_LEVELS,
    STATUSES,
    SUPPORTED_ACTIONS,
    make_shape_uid,
)


class OptimizationPlanError(Exception):
    pass


REQUIRED_PLAN_FIELDS = {
    "plan_version",
    "input_geometry_path",
    "output_geometry_path",
    "optimization_mode",
    "created_at",
    "safety_level",
    "shape_count_before",
    "proposed_change_count",
    "applied_change_count",
    "changes",
    "warnings",
}

REQUIRED_CHANGE_FIELDS = {
    "change_id",
    "action",
    "shape_index",
    "shape_uid",
    "shape_type",
    "reason",
    "risk_level",
    "status",
    "before",
    "after",
    "rollback",
    "metadata",
}


def write_optimization_plan(plan, path, overwrite=False):
    validate_optimization_plan(plan)
    plan_path = Path(path)
    if plan_path.exists() and not overwrite:
        raise OptimizationPlanError(f"Optimization plan already exists: {plan_path}")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"plan_path": str(plan_path), "proposed_change_count": plan["proposed_change_count"]}


def read_optimization_plan(path):
    plan_path = Path(path)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OptimizationPlanError(f"Invalid optimization plan JSON: {plan_path}") from exc
    validate_optimization_plan(plan)
    return plan


def validate_optimization_plan(plan, geometry=None, allow_destructive=False):
    if not isinstance(plan, dict):
        raise OptimizationPlanError("Optimization plan must be an object.")
    missing = sorted(REQUIRED_PLAN_FIELDS - set(plan))
    if missing:
        raise OptimizationPlanError(f"Optimization plan missing required fields: {missing}")
    if plan.get("safety_level") not in {"safe", "review_required", "destructive"}:
        raise OptimizationPlanError("Invalid plan safety_level.")
    changes = plan.get("changes")
    if not isinstance(changes, list):
        raise OptimizationPlanError("Plan changes must be a list.")
    if plan.get("proposed_change_count") != len(changes):
        raise OptimizationPlanError("proposed_change_count does not match changes length.")
    applied_count = sum(1 for change in changes if change.get("status") == "applied")
    if plan.get("applied_change_count") != applied_count:
        raise OptimizationPlanError("applied_change_count does not match applied changes.")

    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else None
    for index, change in enumerate(changes):
        _validate_change(change, index, shapes, allow_destructive)
    return True


def _validate_change(change, index, shapes, allow_destructive):
    if not isinstance(change, dict):
        raise OptimizationPlanError(f"Change {index} must be an object.")
    missing = sorted(REQUIRED_CHANGE_FIELDS - set(change))
    if missing:
        raise OptimizationPlanError(f"Change {index} missing required fields: {missing}")
    action = change.get("action")
    if action not in SUPPORTED_ACTIONS:
        raise OptimizationPlanError(f"Change {index} has unsupported action: {action}")
    if action in {"remove_shape", "update_shape", "add_shape"} and not allow_destructive:
        raise OptimizationPlanError(f"Destructive change is not allowed by default: {action}")
    if change.get("risk_level") not in RISK_LEVELS:
        raise OptimizationPlanError(f"Change {index} has invalid risk_level.")
    if change.get("status") not in STATUSES:
        raise OptimizationPlanError(f"Change {index} has invalid status.")
    shape_index = change.get("shape_index")
    if shapes is not None and shape_index is not None:
        if not isinstance(shape_index, int) or shape_index < 0 or shape_index >= len(shapes):
            raise OptimizationPlanError(f"Change {index} shape_index is out of range.")
        expected_uid = make_shape_uid(shapes[shape_index], shape_index)
        if change.get("shape_uid") and change.get("shape_uid") != expected_uid:
            raise OptimizationPlanError(f"Change {index} shape_uid does not match geometry.")
