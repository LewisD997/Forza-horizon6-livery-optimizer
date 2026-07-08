import argparse
import json
import sys
from pathlib import Path


VALID_STATUSES = {"completed", "completed_with_warnings", "no_candidates", "failed"}
VALID_DECISIONS = {"safe_to_remove", "probably_safe", "risky", "failed", "not_applicable"}


def main():
    parser = argparse.ArgumentParser(description="Validate per_candidate_ablation_report.json.")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    try:
        report = _load_json(Path(args.report))
        validate_per_candidate_ablation_report(report)
    except Exception as exc:
        print(f"Per-candidate ablation validation failed: {exc}", file=sys.stderr)
        return 1

    print("Per-candidate ablation validation passed.")
    print(f"Status: {report['status']}")
    print(f"Candidates: {len(report['results'])}")
    print(f"Risky: {len(report['summary']['risky'])}")
    return 0


def validate_per_candidate_ablation_report(report):
    required = {
        "ablation_version",
        "status",
        "input_paths",
        "output_dir",
        "candidate_count",
        "results",
        "summary",
        "batch_reference",
        "safety",
        "warnings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise ValueError(f"Report missing fields: {missing}")
    if report["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {report['status']}")
    safety = report["safety"]
    if safety.get("sandbox_only") is not True:
        raise ValueError("safety.sandbox_only must be true.")
    if safety.get("official_cleanup_output_written") is not False:
        raise ValueError("official_cleanup_output_written must be false.")
    if safety.get("original_geometry_modified") is not False:
        raise ValueError("original_geometry_modified must be false.")
    if safety.get("original_feedback_modified") is not False:
        raise ValueError("original_feedback_modified must be false.")
    if report["candidate_count"] != len(report["results"]):
        raise ValueError("candidate_count does not match results length.")
    _validate_results(report["results"])
    _validate_summary(report)
    output_dir = Path(report["output_dir"])
    if (output_dir / "optimized_geometry.json").exists():
        raise ValueError("Workflow must not write optimized_geometry.json.")
    return True


def _validate_results(results):
    for result in results:
        for field in ("change_id", "removal", "impact", "outputs", "warnings"):
            if field not in result:
                raise ValueError(f"Result missing field: {field}")
        removal = result["removal"]
        impact = result["impact"]
        decision = impact.get("overall_decision")
        if decision not in VALID_DECISIONS:
            raise ValueError(f"Invalid impact decision: {decision}")
        if removal.get("status") in {"completed", "completed_with_warnings"}:
            if removal.get("simulated_removed_count") != 1:
                raise ValueError(f"Completed candidate must remove exactly one shape: {result['change_id']}")
            expected = removal.get("input_shape_count") - 1
            if removal.get("output_shape_count") != expected:
                raise ValueError(f"Output shape count is inconsistent: {result['change_id']}")
            for key in ("sandbox_geometry", "before_preview", "after_preview", "diff", "removal_report", "impact_report"):
                path = result["outputs"].get(key)
                if not path or not Path(path).exists():
                    raise ValueError(f"Expected output missing for {result['change_id']}: {key}")


def _validate_summary(report):
    summary = report["summary"]
    for key in ("safe_to_remove", "probably_safe", "risky", "failed", "not_applicable", "best_candidates", "worst_candidates"):
        if key not in summary or not isinstance(summary[key], list):
            raise ValueError(f"Summary missing list: {key}")
    counted = []
    for key in ("safe_to_remove", "probably_safe", "risky", "failed", "not_applicable"):
        counted.extend(summary[key])
    result_ids = [item.get("change_id") for item in report["results"]]
    if sorted(counted) != sorted(result_ids):
        raise ValueError("Summary decision groups do not match results.")


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
