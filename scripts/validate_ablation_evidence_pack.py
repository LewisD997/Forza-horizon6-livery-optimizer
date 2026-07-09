import argparse
import json
import sys
from pathlib import Path

VALID_STATUSES = {"completed", "completed_with_warnings", "no_candidates", "failed"}
VALID_TRIAGE = {
    "safe_delete_candidate",
    "visible_but_minor",
    "needs_replacement",
    "protect_candidate",
    "unclear_needs_review",
}


def main():
    parser = argparse.ArgumentParser(description="Validate ablation evidence pack report.")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    try:
        report = _load_json(Path(args.report))
        validate_ablation_evidence_pack_report(report)
    except Exception as exc:
        print(f"Ablation evidence pack validation failed: {exc}", file=sys.stderr)
        return 1

    print("Ablation evidence pack validation passed.")
    print(f"Status: {report['status']}")
    print(f"Candidates: {report['candidate_count']}")
    print(f"Triage counts: {report['triage_counts']}")
    return 0


def validate_ablation_evidence_pack_report(report):
    required = {
        "evidence_pack_version",
        "status",
        "source_ablation_report",
        "candidate_count",
        "triage_counts",
        "candidates",
        "assistant_review_pack",
        "safety",
        "warnings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise ValueError(f"Report missing fields: {missing}")
    if report["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {report['status']}")
    safety = report["safety"]
    if safety.get("evidence_only") is not True:
        raise ValueError("safety.evidence_only must be true.")
    if safety.get("official_cleanup_output_written") is not False:
        raise ValueError("official_cleanup_output_written must be false.")
    if safety.get("original_geometry_modified") is not False:
        raise ValueError("original_geometry_modified must be false.")
    if safety.get("original_feedback_modified") is not False:
        raise ValueError("original_feedback_modified must be false.")
    if report["candidate_count"] != len(report["candidates"]):
        raise ValueError("candidate_count does not match candidates length.")
    _validate_triage_counts(report)
    _validate_candidates(report["candidates"])
    _validate_assistant_pack(report["assistant_review_pack"])
    output_root = Path(report["assistant_review_pack"].get("manifest", ".")).parents[1]
    if (output_root / "optimized_geometry.json").exists():
        raise ValueError("Evidence workflow must not write optimized_geometry.json.")
    return True


def _validate_triage_counts(report):
    counts = report["triage_counts"]
    for decision in VALID_TRIAGE:
        if decision not in counts or not isinstance(counts[decision], int):
            raise ValueError(f"triage_counts missing: {decision}")
    expected = {decision: 0 for decision in VALID_TRIAGE}
    for candidate in report["candidates"]:
        decision = candidate.get("triage_decision")
        if decision not in VALID_TRIAGE:
            raise ValueError(f"Invalid triage decision: {decision}")
        expected[decision] += 1
    if counts != expected:
        raise ValueError("triage_counts does not match candidates.")


def _validate_candidates(candidates):
    for candidate in candidates:
        for field in ("change_id", "triage_decision", "triage_confidence", "triage_reasons", "outputs"):
            if field not in candidate:
                raise ValueError(f"Candidate missing field: {field}")
        outputs = candidate.get("outputs") or {}
        if outputs:
            for key in (
                "before_crop",
                "after_crop",
                "diff_crop",
                "amplified_diff_crop",
                "candidate_mask_overlay",
                "review_card",
            ):
                path = outputs.get(key)
                if not path or not Path(path).exists():
                    raise ValueError(f"Candidate output missing: {candidate.get('change_id')} {key}")


def _validate_assistant_pack(pack):
    for key in ("manifest", "summary"):
        path = pack.get(key)
        if not path or not Path(path).exists():
            raise ValueError(f"Assistant review pack missing: {key}")
    sheet = pack.get("combined_sheet")
    if sheet and not Path(sheet).exists():
        raise ValueError("Assistant review sheet missing.")


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
