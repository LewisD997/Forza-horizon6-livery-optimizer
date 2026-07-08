import copy
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.trial_feedback_generator import generate_trial_feedback
from engine.output.trial_feedback_writer import validate_trial_feedback
from scripts.run_trial_accepted_workflow import run_workflow
from scripts.validate_trial_workflow import validate_trial_workflow_report


def main():
    test_trial_feedback_selects_conservative_unsure_candidates()
    test_protected_and_rejected_candidates_are_not_selected()
    test_explicit_change_ids_select_safe_items()
    test_explicit_change_ids_skip_unsafe_items()
    test_trial_workflow_writes_sandbox_outputs_without_touching_inputs()
    test_trial_workflow_handles_no_eligible_candidates()
    print("Trial accepted candidate workflow smoke test passed.")
    return 0


def test_trial_feedback_selects_conservative_unsure_candidates():
    plan = _plan()
    feedback = _feedback({"C0001": "unsure", "C0002": "unsure", "C0003": "protected"})
    original = copy.deepcopy(feedback)
    result = generate_trial_feedback(plan, feedback, options={"max_trial_accepts": 1})
    selected = result["selected_trial_candidates"]
    assert len(selected) == 1
    assert selected[0]["change_id"] == "C0001"
    assert feedback == original
    assert result["trial_feedback"]["counts_by_status"]["accepted"] == 1
    assert result["trial_feedback"]["counts_by_status"]["unsure"] == 1
    validate_trial_feedback(result["trial_feedback"], feedback, plan)


def test_protected_and_rejected_candidates_are_not_selected():
    plan = _plan()
    feedback = _feedback({"C0001": "protected", "C0002": "rejected", "C0003": "unsure"})
    result = generate_trial_feedback(plan, feedback, options={"max_trial_accepts": 3})
    selected_ids = {item["change_id"] for item in result["selected_trial_candidates"]}
    skipped = {item["change_id"]: item["reason"] for item in result["skipped_candidates"]}
    assert "C0001" not in selected_ids
    assert "C0002" not in selected_ids
    assert skipped["C0001"] == "feedback_status_protected_blocked"
    assert skipped["C0002"] == "feedback_status_rejected_blocked"


def test_explicit_change_ids_select_safe_items():
    plan = _plan()
    feedback = _feedback({"C0001": "unsure", "C0002": "unsure", "C0003": "unsure"})
    result = generate_trial_feedback(plan, feedback, options={"change_ids": "C0002"})
    selected = result["selected_trial_candidates"]
    assert [item["change_id"] for item in selected] == ["C0002"]
    assert result["trial_feedback"]["counts_by_status"]["accepted"] == 1


def test_explicit_change_ids_skip_unsafe_items():
    plan = _plan()
    feedback = _feedback({"C0001": "protected", "C0002": "rejected"})
    result = generate_trial_feedback(plan, feedback, options={"change_ids": "C0001,C0002,missing"})
    assert result["selected_trial_candidates"] == []
    reasons = {item["change_id"]: item["reason"] for item in result["skipped_candidates"]}
    assert reasons["C0001"] == "feedback_status_protected_blocked"
    assert reasons["C0002"] == "feedback_status_rejected_blocked"
    assert reasons["missing"] == "change_id_not_found_in_plan"


def test_trial_workflow_writes_sandbox_outputs_without_touching_inputs():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir), accepted_status="unsure")
        original_geometry = _load(case_dir / "paintstudio_geometry.json")
        original_feedback = _load(case_dir / "candidate_review" / "candidate_feedback.json")
        report = run_workflow(_args(case_dir, max_trial_accepts=2))

        validate_trial_workflow_report(report)
        assert report["status"] in {"completed", "completed_with_warnings"}
        assert len(report["selected_trial_candidates"]) == 2
        assert report["removal_summary"]["simulated_removed_count"] == 2
        assert report["removal_summary"]["output_shape_count"] == report["removal_summary"]["input_shape_count"] - 2
        assert report["impact_summary"]["status"] == "completed"
        assert (case_dir / "removal_simulation" / "trial" / "candidate_feedback_trial.json").exists()
        assert (case_dir / "removal_simulation" / "trial" / "sandbox_removed_geometry_trial.json").exists()
        assert (case_dir / "removal_simulation" / "trial" / "before_preview.png").exists()
        assert (case_dir / "removal_simulation" / "trial" / "after_preview.png").exists()
        assert (case_dir / "removal_simulation" / "trial" / "diff.png").exists()
        assert _load(case_dir / "paintstudio_geometry.json") == original_geometry
        assert _load(case_dir / "candidate_review" / "candidate_feedback.json") == original_feedback


def test_trial_workflow_handles_no_eligible_candidates():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir), accepted_status="protected")
        report = run_workflow(_args(case_dir, max_trial_accepts=2))
        validate_trial_workflow_report(report)
        assert report["status"] == "no_eligible_trial_candidates"
        assert report["removal_summary"]["simulated_removed_count"] == 0
        assert report["impact_summary"]["status"] == "not_applicable_no_removals"


def _args(case_dir, max_trial_accepts=5):
    return SimpleNamespace(
        case=str(case_dir),
        geometry=None,
        plan=None,
        feedback=None,
        output_dir=None,
        max_trial_accepts=max_trial_accepts,
        candidate_type=None,
        risk_level=None,
        change_ids=None,
        allow_review_only=False,
        allow_early_shapes=False,
        overwrite=False,
        preview_renderer="paintstudio-source",
        local_padding=4,
    )


def _write_case(root, accepted_status):
    from PIL import Image

    case_dir = root / "fixture_case"
    review_dir = case_dir / "candidate_review"
    review_dir.mkdir(parents=True)
    Image.new("RGBA", (80, 60), (255, 255, 255, 255)).save(case_dir / "source_full.png")
    geometry = _geometry()
    (case_dir / "paintstudio_geometry.json").write_text(json.dumps(geometry, indent=2), encoding="utf-8")
    plan = _plan()
    (case_dir / "optimization_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    feedback = _feedback({"C0001": accepted_status, "C0002": accepted_status, "C0003": "rejected"})
    (review_dir / "candidate_feedback.json").write_text(json.dumps(feedback, indent=2), encoding="utf-8")
    return case_dir


def _geometry():
    shapes = [{"type": 1, "data": [0, 0, 80, 60], "color": [255, 255, 255, 255], "score": 0}]
    for index in range(1, 24):
        shapes.append(
            {
                "type": 16,
                "data": [10 + index, 12 + (index % 6), 1.0, 1.0, 0, 0],
                "color": [230, 230, 230, 0],
                "score": 0.1,
            }
        )
    shapes[21] = {"type": 16, "data": [30, 24, 2.0, 1.5, 0, 0], "color": [250, 40, 40, 40], "score": 0.4}
    shapes[22] = {"type": 16, "data": [38, 25, 2.0, 1.5, 0, 0], "color": [40, 80, 240, 40], "score": 0.4}
    shapes[23] = {"type": 32, "data": [50, 30, 58, 34, 53, 42], "color": [20, 20, 20, 255], "score": 0.8}
    return {"shapes": shapes}


def _plan():
    return {
        "plan_version": "fixture",
        "changes": [
            _change("C0001", 21, "shape-21", "tiny_fragment_cluster_member", 0.92, "low"),
            _change("C0002", 22, "shape-22", "low_alpha_large_soft_shape", 0.78, "low", alpha=0.12),
            _change("C0003", 23, "shape-23", "ellipse_cluster_member", 0.55, "low"),
        ],
    }


def _change(change_id, shape_index, shape_uid, candidate_type, score, risk_level, alpha=0.18):
    return {
        "change_id": change_id,
        "action": "mark_candidate",
        "shape_index": shape_index,
        "shape_uid": shape_uid,
        "risk_level": risk_level,
        "status": "proposed",
        "metadata": {
            "candidate_type": candidate_type,
            "candidate_score": score,
            "layer_alpha": alpha,
            "layer_area_estimate": 24,
            "region": {"x": 24 + shape_index % 10, "y": 20, "width": 8, "height": 8},
        },
    }


def _feedback(statuses):
    items = []
    for change in _plan()["changes"]:
        items.append(
            {
                "change_id": change["change_id"],
                "shape_index": change["shape_index"],
                "shape_uid": change["shape_uid"],
                "candidate_type": change["metadata"]["candidate_type"],
                "status": statuses.get(change["change_id"], "unsure"),
                "reviewer_note": "",
                "reviewed_at": None,
                "metadata": {},
            }
        )
    counts = {status: 0 for status in ("accepted", "protected", "rejected", "unsure")}
    for item in items:
        counts[item["status"]] += 1
    return {
        "feedback_version": "fixture",
        "total_feedback_items": len(items),
        "counts_by_status": counts,
        "items": items,
    }


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
