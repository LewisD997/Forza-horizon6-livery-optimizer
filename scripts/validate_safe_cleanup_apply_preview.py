import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from engine.optimizer.change_plan import make_shape_uid
from engine.optimizer.safe_cleanup_preview_applier import reconstruct_original_from_preview


def validate_safe_cleanup_apply_preview(report, original):
    required = {"apply_preview_version", "status", "input_paths", "output_paths", "input_shape_count", "proposal_candidate_count",
                "applied_removal_count", "skipped_removal_count", "output_shape_count", "applied_change_ids", "preview_impact",
                "reference_comparison", "rollback_validation", "safety", "warnings"}
    missing = sorted(required - set(report))
    if missing: raise ValueError(f"Report missing fields: {missing}")
    outputs = report["output_paths"]
    preview_path = Path(outputs["preview_geometry"])
    if preview_path.name.lower() == "optimized_geometry.json": raise ValueError("Preview uses forbidden optimized_geometry.json name.")
    preview = _load(preview_path); ledger = _load(Path(outputs["ledger"]))
    proposal = _load(Path(report["input_paths"]["proposal"]))
    proposed_keys = {(item.get("change_id"), item.get("shape_uid")) for item in proposal.get("proposed_removals", [])}
    blocked_keys = {(item.get("change_id"), item.get("shape_uid")) for item in proposal.get("blocked_removals", [])}
    safety = report["safety"]
    for key in ("original_geometry_modified", "original_feedback_modified", "input_proposal_modified", "official_cleanup_output_written"):
        if safety.get(key) is not False: raise ValueError(f"safety.{key} must be false.")
    if safety.get("output_is_preview_only") is not True: raise ValueError("Output must be preview-only.")
    if report["output_shape_count"] != report["input_shape_count"] - report["applied_removal_count"]: raise ValueError("Shape counts are inconsistent.")
    if len(ledger) != report["applied_removal_count"]: raise ValueError("Ledger count mismatch.")
    for item in ledger:
        index = item["original_shape_index"]
        identity = (item.get("change_id"), item.get("shape_uid"))
        if identity not in proposed_keys: raise ValueError("Applied removal is not in proposed_removals.")
        if identity in blocked_keys: raise ValueError("A blocked removal was applied.")
        if make_shape_uid(original["shapes"][index], index) != item["shape_uid"]: raise ValueError("Ledger shape UID mismatch.")
        checks = item.get("validation_checks") or {}
        if not checks or not all(checks.values()): raise ValueError("An applied removal failed a safety check.")
    reconstructed = reconstruct_original_from_preview(preview, ledger)
    if reconstructed != original: raise ValueError("Rollback reconstruction does not match original geometry.")
    if not Path(outputs["rollback_geometry"]).exists(): raise ValueError("Rollback geometry is missing.")
    reference = report["reference_comparison"]
    if reference.get("status") not in {"completed", "not_available"}: raise ValueError("Invalid reference comparison status.")
    for key in ("before_preview", "after_preview", "diff"):
        path = outputs.get(key)
        if report["preview_impact"].get("overall_decision") != "not_applicable" and (not path or not Path(path).exists()): raise ValueError(f"Rendered output missing: {key}")
    return True


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--report", required=True); parser.add_argument("--original", required=True)
    args = parser.parse_args()
    try: validate_safe_cleanup_apply_preview(_load(Path(args.report)), _load(Path(args.original)))
    except Exception as exc: print(f"Safe cleanup apply preview validation failed: {exc}", file=sys.stderr); return 1
    print("Safe cleanup apply preview validation passed."); return 0


def _load(path): return json.loads(path.read_text(encoding="utf-8"))
if __name__ == "__main__": raise SystemExit(main())
