import copy
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_per_candidate_ablation import run_from_args
from scripts.validate_per_candidate_ablation import validate_per_candidate_ablation_report


def main():
    test_runs_three_candidates_individually()
    test_protected_and_rejected_candidates_are_skipped()
    test_explicit_change_ids_override_trial_report()
    test_no_candidates_report()
    print("Per-candidate ablation smoke test passed.")
    return 0


def test_runs_three_candidates_individually():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir))
        original_geometry = _load(case_dir / "paintstudio_geometry.json")
        original_feedback = _load(case_dir / "candidate_review" / "candidate_feedback.json")
        report = run_from_args(_args(case_dir))

        validate_per_candidate_ablation_report(report)
        assert report["status"] in {"completed", "completed_with_warnings"}
        assert report["candidate_count"] == 3
        assert len(report["results"]) == 3
        for result in report["results"]:
            assert result["removal"]["simulated_removed_count"] == 1
            assert result["removal"]["output_shape_count"] == result["removal"]["input_shape_count"] - 1
            assert result["impact"]["overall_decision"] in {"safe_to_remove", "probably_safe", "risky"}
        grouped = (
            report["summary"]["safe_to_remove"]
            + report["summary"]["probably_safe"]
            + report["summary"]["risky"]
            + report["summary"]["failed"]
            + report["summary"]["not_applicable"]
        )
        assert sorted(grouped) == sorted(["C0001", "C0002", "C0003"])
        assert report["summary"]["best_candidates"]
        assert report["summary"]["worst_candidates"]
        assert _load(case_dir / "paintstudio_geometry.json") == original_geometry
        assert _load(case_dir / "candidate_review" / "candidate_feedback.json") == original_feedback


def test_protected_and_rejected_candidates_are_skipped():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir), statuses={"C0001": "protected", "C0002": "rejected", "C0003": "unsure"})
        report = run_from_args(_args(case_dir, change_ids="C0001,C0002,C0003"))
        validate_per_candidate_ablation_report(report)
        skipped = {item["change_id"]: item for item in report["results"] if item["removal"]["status"] == "skipped"}
        assert set(skipped) == {"C0001", "C0002"}
        completed = [item for item in report["results"] if item["removal"]["status"] != "skipped"]
        assert len(completed) == 1
        assert completed[0]["change_id"] == "C0003"
        assert completed[0]["removal"]["simulated_removed_count"] == 1


def test_explicit_change_ids_override_trial_report():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir))
        report = run_from_args(_args(case_dir, change_ids="C0002"))
        validate_per_candidate_ablation_report(report)
        assert [item["change_id"] for item in report["results"]] == ["C0002"]


def test_no_candidates_report():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir), selected=[])
        report = run_from_args(_args(case_dir))
        validate_per_candidate_ablation_report(report)
        assert report["status"] == "no_candidates"
        assert report["candidate_count"] == 0
        assert report["results"] == []


def _args(case_dir, change_ids=None):
    return SimpleNamespace(
        case=str(case_dir),
        geometry=None,
        plan=None,
        feedback=None,
        trial_report=None,
        output_dir=None,
        change_ids=change_ids,
        max_candidates=5,
        candidate_type=None,
        risk_level=None,
        overwrite=False,
        preview_renderer="paintstudio-source",
        local_padding=4,
        safe_threshold=None,
        probably_safe_threshold=None,
        risky_threshold=None,
    )


def _write_case(root, statuses=None, selected=None):
    from PIL import Image

    statuses = statuses or {"C0001": "unsure", "C0002": "unsure", "C0003": "unsure"}
    selected = ["C0001", "C0002", "C0003"] if selected is None else selected
    case_dir = root / "fixture_case"
    review_dir = case_dir / "candidate_review"
    trial_dir = case_dir / "removal_simulation" / "trial"
    review_dir.mkdir(parents=True)
    trial_dir.mkdir(parents=True)
    Image.new("RGBA", (80, 60), (255, 255, 255, 255)).save(case_dir / "source_full.png")
    (case_dir / "paintstudio_geometry.json").write_text(json.dumps(_geometry(), indent=2), encoding="utf-8")
    (case_dir / "optimization_plan.json").write_text(json.dumps(_plan(), indent=2), encoding="utf-8")
    (review_dir / "candidate_feedback.json").write_text(json.dumps(_feedback(statuses), indent=2), encoding="utf-8")
    (trial_dir / "trial_workflow_report.json").write_text(
        json.dumps(_trial_report(selected), indent=2),
        encoding="utf-8",
    )
    return case_dir


def _geometry():
    return {
        "shapes": [
            {"type": 1, "data": [0, 0, 80, 60], "color": [255, 255, 255, 255], "score": 0},
            {"type": 16, "data": [18, 20, 1.0, 1.0, 0, 0], "color": [0, 0, 0, 0], "score": 0.1},
            {"type": 16, "data": [32, 22, 2.0, 2.0, 0, 0], "color": [230, 30, 30, 40], "score": 0.2},
            {"type": 2, "data": [50, 34, 8.0, 6.0, 0, 0], "color": [20, 20, 20, 255], "score": 0.7},
        ]
    }


def _plan():
    return {
        "plan_version": "fixture",
        "changes": [
            _change("C0001", 1, "shape-1", "tiny_fragment_cluster_member", 0.95, 8, 8, 0.0),
            _change("C0002", 2, "shape-2", "low_alpha_large_soft_shape", 0.82, 28, 18, 0.15),
            _change("C0003", 3, "shape-3", "ellipse_cluster_member", 0.72, 42, 28, 1.0),
        ],
    }


def _change(change_id, shape_index, shape_uid, candidate_type, score, x, y, alpha):
    return {
        "change_id": change_id,
        "action": "mark_candidate",
        "shape_index": shape_index,
        "shape_uid": shape_uid,
        "risk_level": "low",
        "status": "proposed",
        "metadata": {
            "candidate_type": candidate_type,
            "candidate_score": score,
            "layer_alpha": alpha,
            "layer_area_estimate": 64,
            "region": {"x": x, "y": y, "width": 20, "height": 20},
        },
    }


def _feedback(statuses):
    items = []
    for change in _plan()["changes"]:
        status = statuses.get(change["change_id"], "unsure")
        items.append(
            {
                "change_id": change["change_id"],
                "shape_index": change["shape_index"],
                "shape_uid": change["shape_uid"],
                "candidate_type": change["metadata"]["candidate_type"],
                "status": status,
                "reviewer_note": "",
                "reviewed_at": None,
                "metadata": {},
            }
        )
    counts = {status: 0 for status in ("accepted", "protected", "rejected", "unsure")}
    for item in items:
        counts[item["status"]] += 1
    return {"feedback_version": "fixture", "total_feedback_items": len(items), "counts_by_status": counts, "items": items}


def _trial_report(selected):
    by_id = {change["change_id"]: change for change in _plan()["changes"]}
    return {
        "trial_version": "0.6.8",
        "status": "completed" if selected else "no_eligible_trial_candidates",
        "selected_trial_candidates": [
            {
                "change_id": change_id,
                "shape_index": by_id[change_id]["shape_index"],
                "shape_uid": by_id[change_id]["shape_uid"],
                "candidate_type": by_id[change_id]["metadata"]["candidate_type"],
                "risk_level": by_id[change_id]["risk_level"],
                "trial_score": 6,
            }
            for change_id in selected
        ],
        "impact_summary": {
            "overall_decision": "risky",
            "global_changed_pixel_ratio": 0.05,
        },
    }


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
