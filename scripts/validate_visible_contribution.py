import argparse
import json
import sys
from pathlib import Path

CONTRIBUTION_CLASSES = {
    "zero_or_negligible_contribution",
    "barely_visible_contribution",
    "visible_minor_contribution",
    "important_visible_contribution",
    "critical_contribution",
    "scan_failed",
}

RECOMMENDED_ACTIONS = {
    "safe_delete_pool",
    "deletion_candidate_review",
    "replacement_candidate",
    "protect_candidate",
    "unclear_needs_review",
}

VALID_STATUSES = {"completed", "completed_with_warnings", "no_shapes_to_scan", "failed"}


def main():
    parser = argparse.ArgumentParser(description="Validate visible_contribution_report.json.")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        report = _load_json(Path(args.report))
        validate_visible_contribution_report(report)
    except Exception as exc:
        print(f"Visible contribution validation failed: {exc}", file=sys.stderr)
        return 1

    print("Visible contribution validation passed.")
    print(f"Status: {report['status']}")
    print(f"Scanned: {report['scanned_shape_count']}")
    print(f"Safe delete pool: {len(report['summary']['safe_delete_pool'])}")
    return 0


def validate_visible_contribution_report(report):
    required = {
        "visible_contribution_version",
        "status",
        "scan_scope",
        "input_paths",
        "shape_count",
        "scanned_shape_count",
        "results",
        "summary",
        "thresholds",
        "safety",
        "warnings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise ValueError(f"Report missing fields: {missing}")
    if report["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {report['status']}")
    if report["scanned_shape_count"] != len(report["results"]):
        raise ValueError("scanned_shape_count does not match results length.")
    safety = report["safety"]
    if safety.get("sandbox_only") is not True:
        raise ValueError("safety.sandbox_only must be true.")
    if safety.get("official_cleanup_output_written") is not False:
        raise ValueError("official_cleanup_output_written must be false.")
    if safety.get("original_geometry_modified") is not False:
        raise ValueError("original_geometry_modified must be false.")
    _validate_results(report["results"])
    _validate_summary(report)
    return True


def _validate_results(results):
    for result in results:
        for field in (
            "shape_index",
            "global_metrics",
            "local_metrics",
            "contribution_class",
            "recommended_action",
            "outputs",
            "warnings",
        ):
            if field not in result:
                raise ValueError(f"Result missing field: {field}")
        if result["contribution_class"] not in CONTRIBUTION_CLASSES:
            raise ValueError(f"Invalid contribution class: {result['contribution_class']}")
        if result["recommended_action"] not in RECOMMENDED_ACTIONS:
            raise ValueError(f"Invalid recommended action: {result['recommended_action']}")
        if result.get("removed_shape_count") not in {0, 1}:
            raise ValueError("A scan result must remove zero or one shape.")
        if result["contribution_class"] != "scan_failed":
            for key in ("after_preview", "diff", "diff_crop", "amplified_diff_crop", "evidence_card", "metadata"):
                path = result["outputs"].get(key)
                if not path or not Path(path).exists():
                    raise ValueError(f"Expected output missing for shape {result.get('shape_index')}: {key}")


def _validate_summary(report):
    summary = report["summary"]
    for key in CONTRIBUTION_CLASSES | RECOMMENDED_ACTIONS:
        if key not in summary or not isinstance(summary[key], list):
            raise ValueError(f"Summary missing list: {key}")
    class_ids = []
    action_ids = []
    for key in CONTRIBUTION_CLASSES:
        class_ids.extend(summary[key])
    for key in RECOMMENDED_ACTIONS:
        action_ids.extend(summary[key])
    result_ids = [_ident(result) for result in report["results"]]
    if sorted(class_ids) != sorted(result_ids):
        raise ValueError("Contribution class summary does not match results.")
    if sorted(action_ids) != sorted(result_ids):
        raise ValueError("Recommended action summary does not match results.")


def _ident(result):
    return result.get("change_id") or f"shape_{result.get('shape_index')}"


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
