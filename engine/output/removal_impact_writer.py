import json
from pathlib import Path


class RemovalImpactWriteError(Exception):
    pass


VALID_STATUSES = {"completed", "not_applicable_no_removals", "missing_inputs", "failed"}
VALID_DECISIONS = {"safe_to_remove", "probably_safe", "risky", "failed", "not_applicable"}


def write_removal_impact_report(report, path, overwrite=False):
    validate_removal_impact_report(report)
    output_path = Path(path)
    if output_path.exists() and not overwrite:
        raise RemovalImpactWriteError(f"Removal impact report already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(output_path)


def validate_removal_impact_report(report):
    if not isinstance(report, dict):
        raise RemovalImpactWriteError("Removal impact report must be an object.")
    required = {
        "impact_version",
        "status",
        "overall_decision",
        "input_paths",
        "shape_counts",
        "global_metrics",
        "local_metrics",
        "per_removed_shape_metrics",
        "thresholds",
        "warnings",
        "recommendations",
    }
    missing = sorted(required - set(report))
    if missing:
        raise RemovalImpactWriteError(f"Removal impact report missing fields: {missing}")
    if report["status"] not in VALID_STATUSES:
        raise RemovalImpactWriteError(f"Invalid impact status: {report['status']}")
    if report["overall_decision"] not in VALID_DECISIONS:
        raise RemovalImpactWriteError(f"Invalid impact decision: {report['overall_decision']}")
    _validate_shape_counts(report["shape_counts"], report["status"])
    _validate_thresholds(report["thresholds"])
    _validate_metric_keys(report["global_metrics"], report["local_metrics"])
    if report["status"] == "completed":
        for key in ("mean_abs_diff", "max_abs_diff", "changed_pixel_count", "changed_pixel_ratio"):
            if not isinstance(report["global_metrics"].get(key), (int, float)):
                raise RemovalImpactWriteError(f"Completed impact report missing numeric metric: {key}")
    if "approval" in report or "cleanup_approved" in report or "apply_cleanup" in report:
        raise RemovalImpactWriteError("Impact report must not contain cleanup approval fields.")
    return True


def _validate_shape_counts(shape_counts, status):
    required = {"input_shape_count", "output_shape_count", "simulated_removed_count"}
    missing = sorted(required - set(shape_counts or {}))
    if missing:
        raise RemovalImpactWriteError(f"shape_counts missing fields: {missing}")
    if status == "not_applicable_no_removals" and shape_counts.get("simulated_removed_count") != 0:
        raise RemovalImpactWriteError("not_applicable_no_removals requires simulated_removed_count = 0.")


def _validate_thresholds(thresholds):
    for key in (
        "safe_changed_pixel_ratio",
        "probably_safe_changed_pixel_ratio",
        "risky_changed_pixel_ratio",
    ):
        if not isinstance((thresholds or {}).get(key), (int, float)):
            raise RemovalImpactWriteError(f"Threshold must be numeric: {key}")


def _validate_metric_keys(global_metrics, local_metrics):
    for key in (
        "mean_abs_diff",
        "max_abs_diff",
        "changed_pixel_count",
        "changed_pixel_ratio",
        "alpha_changed_pixel_ratio",
        "rgb_changed_pixel_ratio",
    ):
        if key not in global_metrics:
            raise RemovalImpactWriteError(f"global_metrics missing: {key}")
    for key in ("mean_local_diff", "max_local_diff", "changed_local_pixel_ratio"):
        if key not in local_metrics:
            raise RemovalImpactWriteError(f"local_metrics missing: {key}")
