import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate trial_workflow_report.json.")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    try:
        report = _load_json(Path(args.report))
        validate_trial_workflow_report(report)
    except Exception as exc:
        print(f"Trial workflow validation failed: {exc}", file=sys.stderr)
        return 1

    print("Trial workflow validation passed.")
    print(f"Status: {report['status']}")
    print(f"Selected: {len(report['selected_trial_candidates'])}")
    print(f"Removed: {report['removal_summary']['simulated_removed_count']}")
    return 0


def validate_trial_workflow_report(report):
    required = {
        "trial_version",
        "status",
        "input_paths",
        "output_paths",
        "original_feedback_counts",
        "trial_feedback_counts",
        "selected_trial_candidates",
        "skipped_candidates",
        "removal_summary",
        "impact_summary",
        "safety",
        "warnings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise ValueError(f"Report missing fields: {missing}")
    safety = report["safety"]
    if safety.get("trial_feedback_only") is not True:
        raise ValueError("trial_feedback_only must be true.")
    if safety.get("official_cleanup_output_written") is not False:
        raise ValueError("official_cleanup_output_written must be false.")
    if safety.get("original_geometry_modified") is not False:
        raise ValueError("original_geometry_modified must be false.")
    if safety.get("original_feedback_modified") is not False:
        raise ValueError("original_feedback_modified must be false.")
    removal = report["removal_summary"]
    if report["status"] in {"completed", "completed_with_warnings"}:
        if len(report["selected_trial_candidates"]) <= 0:
            raise ValueError("Completed trial must select candidates.")
        if removal["simulated_removed_count"] <= 0:
            raise ValueError("Completed trial must remove shapes in sandbox.")
        expected = removal["input_shape_count"] - removal["simulated_removed_count"]
        if removal["output_shape_count"] != expected:
            raise ValueError("Output shape count is inconsistent.")
        impact_path = report["output_paths"].get("removal_impact_report")
        if not impact_path or not Path(impact_path).exists():
            raise ValueError("Impact report must exist for completed trial.")
    if report["status"] == "no_eligible_trial_candidates" and removal["simulated_removed_count"] != 0:
        raise ValueError("No eligible candidates must remove zero shapes.")
    return True


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
