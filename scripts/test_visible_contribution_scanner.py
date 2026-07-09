import copy
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.visible_contribution_scanner import scan_visible_contribution
from scripts.scan_visible_contribution import run_from_args
from scripts.validate_visible_contribution import validate_visible_contribution_report


def main():
    test_scans_explicit_shape_ids_and_preserves_inputs()
    test_excludes_protected_and_rejected_feedback()
    test_recommended_action_policy()
    test_missing_render_warns_without_crashing()
    print("Visible contribution scanner smoke test passed.")
    return 0


def test_scans_explicit_shape_ids_and_preserves_inputs():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir))
        geometry = _load(case_dir / "paintstudio_geometry.json")
        feedback = _load(case_dir / "candidate_review" / "candidate_feedback.json")
        original_geometry = copy.deepcopy(geometry)
        original_feedback = copy.deepcopy(feedback)
        report = run_from_args(
            _args(
                case_dir,
                scope="explicit",
                change_ids="C0001,C0002,C0003",
                output_dir=case_dir / "visible_contribution_explicit",
            )
        )
        validate_visible_contribution_report(report)
        assert report["scanned_shape_count"] == 3
        classes = {result["change_id"]: result["contribution_class"] for result in report["results"]}
        assert classes["C0001"] == "zero_or_negligible_contribution"
        assert classes["C0002"] in {"barely_visible_contribution", "visible_minor_contribution", "important_visible_contribution"}
        assert classes["C0003"] == "critical_contribution"
        assert (case_dir / "visible_contribution_explicit" / "visible_contribution_table.csv").exists()
        assert (case_dir / "visible_contribution_explicit" / "evidence_sheet.png").exists()
        assert _load(case_dir / "paintstudio_geometry.json") == original_geometry
        assert _load(case_dir / "candidate_review" / "candidate_feedback.json") == original_feedback


def test_excludes_protected_and_rejected_feedback():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(
            Path(temp_dir),
            statuses={"C0001": "protected", "C0002": "rejected", "C0003": "unsure"},
        )
        report = run_from_args(
            _args(
                case_dir,
                scope="feedback_filtered",
                output_dir=case_dir / "visible_contribution_filtered",
            )
        )
        validate_visible_contribution_report(report)
        assert [result["change_id"] for result in report["results"]] == ["C0003"]


def test_recommended_action_policy():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir))
        report = run_from_args(
            _args(
                case_dir,
                scope="explicit",
                change_ids="C0001,C0002,C0003",
                output_dir=case_dir / "visible_contribution_policy",
            )
        )
        actions = {result["change_id"]: result["recommended_action"] for result in report["results"]}
        assert actions["C0001"] == "safe_delete_pool"
        assert actions["C0002"] == "replacement_candidate"
        assert actions["C0003"] == "protect_candidate"


def test_missing_render_warns_without_crashing():
    geometry = _geometry()
    original = copy.deepcopy(geometry)
    report = scan_visible_contribution(
        geometry,
        plan=_plan(),
        feedback=_feedback(),
        options={
            "scope": "explicit",
            "change_ids": "C0001",
            "output_dir": Path(tempfile.mkdtemp()) / "missing_render",
            "geometry_path": None,
        },
    )
    validate_visible_contribution_report(report)
    assert report["status"] == "completed_with_warnings"
    assert report["results"][0]["contribution_class"] == "scan_failed"
    assert geometry == original


def _args(case_dir, scope, output_dir, change_ids=None):
    return SimpleNamespace(
        case=str(case_dir),
        geometry=None,
        plan=None,
        feedback=None,
        output_dir=str(output_dir),
        scope=scope,
        change_ids=change_ids,
        shape_indexes=None,
        start_index=None,
        end_index=None,
        max_scan_shapes=30,
        exclude_protected=True,
        exclude_rejected=True,
        include_unsure=True,
        include_accepted=True,
        crop_padding=8,
        upscale=2,
        amplify_diff=5.0,
        overwrite=False,
        preview_renderer="paintstudio-source",
        local_padding=4,
        zero_threshold=None,
        barely_threshold=None,
        minor_threshold=None,
        important_threshold=None,
    )


def _write_case(root, statuses=None):
    from PIL import Image

    statuses = statuses or {"C0001": "unsure", "C0002": "unsure", "C0003": "unsure"}
    case_dir = root / "fixture_case"
    review_dir = case_dir / "candidate_review"
    review_dir.mkdir(parents=True)
    Image.new("RGBA", (80, 60), (255, 255, 255, 255)).save(case_dir / "source_full.png")
    (case_dir / "paintstudio_geometry.json").write_text(json.dumps(_geometry(), indent=2), encoding="utf-8")
    (case_dir / "optimization_plan.json").write_text(json.dumps(_plan(), indent=2), encoding="utf-8")
    (review_dir / "candidate_feedback.json").write_text(json.dumps(_feedback(statuses), indent=2), encoding="utf-8")
    return case_dir


def _geometry():
    shapes = [{"type": 1, "data": [0, 0, 80, 60], "color": [255, 255, 255, 255], "score": 0}]
    for index in range(1, 6):
        shapes.append({"type": 16, "data": [5 + index, 5, 1, 1, 0, 0], "color": [0, 0, 0, 0], "score": 0})
    shapes.extend(
        [
            {"type": 16, "data": [12, 12, 2, 2, 0, 0], "color": [0, 0, 0, 0], "score": 0.1},
            {"type": 16, "data": [28, 20, 1, 1, 0, 0], "color": [240, 20, 20, 24], "score": 0.2},
            {"type": 2, "data": [50, 34, 10, 8, 0, 0], "color": [20, 20, 20, 255], "score": 0.8},
        ]
    )
    return {"shapes": shapes}


def _plan():
    return {
        "changes": [
            _change("C0001", 6, "shape-6", "tiny_fragment_cluster_member", 0.0, {"x": 10, "y": 10, "width": 6, "height": 6}),
            _change("C0002", 7, "shape-7", "low_alpha_large_soft_shape", 0.1, {"x": 26, "y": 18, "width": 4, "height": 4}),
            _change("C0003", 8, "shape-8", "low_alpha_large_soft_shape", 1.0, {"x": 40, "y": 26, "width": 20, "height": 16}),
        ]
    }


def _change(change_id, shape_index, shape_uid, candidate_type, alpha, region):
    return {
        "change_id": change_id,
        "action": "mark_candidate",
        "shape_index": shape_index,
        "shape_uid": shape_uid,
        "risk_level": "low",
        "metadata": {
            "candidate_type": candidate_type,
            "candidate_score": 0.8,
            "layer_alpha": alpha,
            "layer_area_estimate": 100,
            "region": region,
        },
    }


def _feedback(statuses=None):
    statuses = statuses or {"C0001": "unsure", "C0002": "unsure", "C0003": "unsure"}
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
    return {"items": items}


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
