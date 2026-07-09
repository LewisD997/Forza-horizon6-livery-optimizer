import argparse
import json
import sys
from pathlib import Path


VALID_STATUSES = {"completed", "completed_with_warnings", "no_safe_delete_candidates", "failed"}
VALID_DECISIONS = {"safe_to_remove", "probably_safe", "risky", "failed", "not_applicable"}
BLOCKED_ACTIONS = {
    "deletion_candidate_review",
    "replacement_candidate",
    "protect_candidate",
    "unclear_needs_review",
}


def main():
    parser = argparse.ArgumentParser(description="Validate safe_delete_pool_validation_report.json.")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    try:
        report = _load_json(Path(args.report))
        validate_safe_delete_pool_report(report)
    except Exception as exc:
        print(f"Safe delete pool report validation failed: {exc}", file=sys.stderr)
        return 1

    print("Safe delete pool report validation passed.")
    print(f"Status: {report['status']}")
    print(f"Simulated removed: {report['simulated_removed_count']}")
    print(f"Impact decision: {report['impact_summary']['overall_decision']}")
    return 0


def validate_safe_delete_pool_report(report):
    required = {
        "safe_delete_validation_version",
        "status",
        "input_paths",
        "output_dir",
        "input_shape_count",
        "safe_delete_candidate_count",
        "simulated_removed_count",
        "output_shape_count",
        "removed_shapes",
        "skipped_candidates",
        "impact_summary",
        "outputs",
        "safety",
        "warnings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise ValueError(f"Report missing fields: {missing}")
    if report["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {report['status']}")
    if report["impact_summary"].get("overall_decision") not in VALID_DECISIONS:
        raise ValueError("Invalid impact decision.")
    _validate_safety(report["safety"])
    if report["output_shape_count"] != report["input_shape_count"] - report["simulated_removed_count"]:
        raise ValueError("output_shape_count must equal input_shape_count - simulated_removed_count.")
    if report["safe_delete_candidate_count"] != len(report["removed_shapes"]):
        raise ValueError("safe_delete_candidate_count does not match removed_shapes length.")
    if report["simulated_removed_count"] != len(report["removed_shapes"]):
        raise ValueError("simulated_removed_count does not match removed_shapes length.")
    _validate_removed_shapes(report["removed_shapes"])
    _validate_outputs(report)
    _validate_proposal(report)
    return True


def _validate_safety(safety):
    if safety.get("sandbox_only") is not True:
        raise ValueError("safety.sandbox_only must be true.")
    if safety.get("proposal_only") is not True:
        raise ValueError("safety.proposal_only must be true.")
    if safety.get("official_cleanup_output_written") is not False:
        raise ValueError("official_cleanup_output_written must be false.")
    if safety.get("original_geometry_modified") is not False:
        raise ValueError("original_geometry_modified must be false.")


def _validate_removed_shapes(removed):
    seen_indexes = set()
    seen_ids = set()
    for item in removed:
        if item.get("recommended_action") != "safe_delete_pool":
            raise ValueError("Every removed shape must have recommended_action == safe_delete_pool.")
        if item.get("recommended_action") in BLOCKED_ACTIONS:
            raise ValueError("Blocked action was included in removed_shapes.")
        if item.get("contribution_class") != "zero_or_negligible_contribution":
            raise ValueError("Every removed shape must be zero_or_negligible_contribution.")
        index = item.get("shape_index")
        change_id = item.get("change_id")
        if index in seen_indexes:
            raise ValueError(f"Duplicate removed shape_index: {index}")
        if change_id in seen_ids:
            raise ValueError(f"Duplicate removed change_id: {change_id}")
        seen_indexes.add(index)
        seen_ids.add(change_id)


def _validate_outputs(report):
    outputs = report["outputs"]
    proposal = outputs.get("cleanup_proposal")
    if not proposal or not Path(proposal).exists():
        raise ValueError("cleanup proposal output is missing.")
    summary = outputs.get("summary")
    if not summary or not Path(summary).exists():
        raise ValueError("summary output is missing.")
    if report["status"] == "completed":
        impact = outputs.get("impact_report")
        if not impact or not Path(impact).exists():
            raise ValueError("completed report requires an impact report.")


def _validate_proposal(report):
    proposal = _load_json(Path(report["outputs"]["cleanup_proposal"]))
    if proposal.get("cleanup_proposal_version") != report["safe_delete_validation_version"]:
        raise ValueError("Proposal version does not match report version.")
    if proposal.get("official_geometry_written") is not False:
        raise ValueError("Proposal must not write official geometry.")
    if proposal.get("approval_required") is not True:
        raise ValueError("Proposal must require approval.")
    proposed = proposal.get("proposed_removals") or []
    if len(proposed) != report["simulated_removed_count"]:
        raise ValueError("Proposal proposed_removals count does not match report.")


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
