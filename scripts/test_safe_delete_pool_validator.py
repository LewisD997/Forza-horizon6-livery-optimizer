import copy
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.change_plan import make_shape_uid
from engine.optimizer.safe_delete_pool_validator import validate_safe_delete_pool
from scripts.validate_safe_delete_pool import run_from_args
from scripts.validate_safe_delete_pool_report import validate_safe_delete_pool_report


def main():
    test_no_safe_delete_candidates()
    test_one_safe_delete_candidate_preserves_original()
    test_protected_candidate_is_blocked()
    test_replacement_and_protect_candidates_are_never_included()
    test_shape_uid_mismatch_is_skipped()
    test_batch_multiple_safe_delete_candidates()
    test_cli_report_validation_passes()
    print("Safe delete pool validator smoke test passed.")
    return 0


def test_no_safe_delete_candidates():
    geometry = _geometry()
    report = validate_safe_delete_pool(
        geometry,
        _visible_report([]),
        options={"output_dir": Path(tempfile.mkdtemp()) / "safe_delete", "no_render": True},
    )
    assert report["status"] == "no_safe_delete_candidates"
    assert report["simulated_removed_count"] == 0
    assert report["safety"]["official_cleanup_output_written"] is False


def test_one_safe_delete_candidate_preserves_original():
    geometry = _geometry()
    original = copy.deepcopy(geometry)
    report = validate_safe_delete_pool(
        geometry,
        _visible_report([_safe_result(1, "C0001")]),
        options={"output_dir": Path(tempfile.mkdtemp()) / "safe_delete", "no_render": True},
    )
    assert report["simulated_removed_count"] == 1
    assert report["output_shape_count"] == len(geometry["shapes"]) - 1
    assert report["removed_shapes"][0]["change_id"] == "C0001"
    proposal = _load(report["outputs"]["cleanup_proposal"])
    assert len(proposal["proposed_removals"]) == 1
    assert geometry == original


def test_protected_candidate_is_blocked():
    geometry = _geometry()
    feedback = {
        "items": [
            {
                "change_id": "C0001",
                "shape_index": 1,
                "shape_uid": make_shape_uid(geometry["shapes"][1], 1),
                "status": "protected",
            }
        ]
    }
    report = validate_safe_delete_pool(
        geometry,
        _visible_report([_safe_result(1, "C0001")]),
        options={"output_dir": Path(tempfile.mkdtemp()) / "safe_delete", "feedback": feedback, "no_render": True},
    )
    assert report["status"] == "no_safe_delete_candidates"
    assert report["skipped_candidates"][0]["reason"] == "feedback_protected"


def test_replacement_and_protect_candidates_are_never_included():
    geometry = _geometry()
    results = [
        _safe_result(1, "C0001"),
        _result(2, "C0002", "visible_minor_contribution", "replacement_candidate"),
        _result(3, "C0003", "critical_contribution", "protect_candidate"),
    ]
    report = validate_safe_delete_pool(
        geometry,
        _visible_report(results),
        options={"output_dir": Path(tempfile.mkdtemp()) / "safe_delete", "no_render": True},
    )
    assert [item["change_id"] for item in report["removed_shapes"]] == ["C0001"]
    assert all(item["recommended_action"] == "safe_delete_pool" for item in report["removed_shapes"])


def test_shape_uid_mismatch_is_skipped():
    geometry = _geometry()
    result = _safe_result(1, "C0001")
    result["shape_uid"] = "wrong"
    report = validate_safe_delete_pool(
        geometry,
        _visible_report([result]),
        options={"output_dir": Path(tempfile.mkdtemp()) / "safe_delete", "no_render": True},
    )
    assert report["simulated_removed_count"] == 0
    assert report["skipped_candidates"][0]["reason"] == "shape_uid_mismatch"


def test_batch_multiple_safe_delete_candidates():
    geometry = _geometry()
    report = validate_safe_delete_pool(
        geometry,
        _visible_report([_safe_result(1, "C0001"), _safe_result(4, "C0004")]),
        options={"output_dir": Path(tempfile.mkdtemp()) / "safe_delete", "no_render": True},
    )
    assert report["simulated_removed_count"] == 2
    assert report["output_shape_count"] == len(geometry["shapes"]) - 2
    indexes = [item["shape_index"] for item in report["removed_shapes"]]
    assert len(indexes) == len(set(indexes))


def test_cli_report_validation_passes():
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = _write_case(Path(temp_dir))
        report = run_from_args(
            SimpleNamespace(
                case=str(case_dir),
                geometry=None,
                visible_report=None,
                feedback=None,
                output_dir=None,
                overwrite=False,
                preview_renderer="paintstudio-source",
                local_padding=4,
                safe_threshold=None,
                probably_safe_threshold=None,
                risky_threshold=None,
                write_sandbox_geometry=True,
                no_render=False,
            )
        )
        validate_safe_delete_pool_report(report)
        assert report["status"] == "completed"
        assert report["impact_summary"]["overall_decision"] in {"safe_to_remove", "probably_safe"}


def _write_case(root):
    from PIL import Image

    case_dir = root / "fixture_case"
    case_dir.mkdir(parents=True)
    (case_dir / "visible_contribution").mkdir()
    (case_dir / "candidate_review").mkdir()
    Image.new("RGBA", (80, 60), (255, 255, 255, 255)).save(case_dir / "source_full.png")
    geometry = _geometry()
    (case_dir / "paintstudio_geometry.json").write_text(json.dumps(geometry, indent=2), encoding="utf-8")
    (case_dir / "visible_contribution" / "visible_contribution_report.json").write_text(
        json.dumps(_visible_report([_safe_result(1, "C0001")]), indent=2),
        encoding="utf-8",
    )
    (case_dir / "candidate_review" / "candidate_feedback.json").write_text(
        json.dumps({"items": []}, indent=2),
        encoding="utf-8",
    )
    return case_dir


def _geometry():
    return {
        "shapes": [
            {"type": 1, "data": [0, 0, 80, 60], "color": [255, 255, 255, 255], "score": 0},
            {"type": 16, "data": [20, 20, 2, 2, 0, 0], "color": [255, 0, 0, 0], "score": 0.1},
            {"type": 16, "data": [35, 20, 3, 3, 0, 0], "color": [255, 0, 0, 80], "score": 0.1},
            {"type": 2, "data": [50, 35, 8, 6, 0, 0], "color": [0, 0, 0, 255], "score": 0.5},
            {"type": 16, "data": [22, 22, 1, 1, 0, 0], "color": [0, 0, 255, 0], "score": 0.1},
        ]
    }


def _visible_report(results):
    summary = {
        "zero_or_negligible_contribution": [],
        "barely_visible_contribution": [],
        "visible_minor_contribution": [],
        "important_visible_contribution": [],
        "critical_contribution": [],
        "scan_failed": [],
        "safe_delete_pool": [],
        "deletion_candidate_review": [],
        "replacement_candidate": [],
        "protect_candidate": [],
        "unclear_needs_review": [],
    }
    for result in results:
        ident = result["change_id"]
        summary[result["contribution_class"]].append(ident)
        summary[result["recommended_action"]].append(ident)
    return {
        "visible_contribution_version": "0.6.11",
        "status": "completed" if results else "no_shapes_to_scan",
        "shape_count": len(_geometry()["shapes"]),
        "scanned_shape_count": len(results),
        "results": results,
        "summary": summary,
    }


def _safe_result(shape_index, change_id):
    return _result(shape_index, change_id, "zero_or_negligible_contribution", "safe_delete_pool")


def _result(shape_index, change_id, contribution_class, recommended_action):
    geometry = _geometry()
    return {
        "change_id": change_id,
        "shape_index": shape_index,
        "shape_uid": make_shape_uid(geometry["shapes"][shape_index], shape_index),
        "candidate_type": "tiny_fragment_cluster_member",
        "contribution_class": contribution_class,
        "recommended_action": recommended_action,
        "removed_shape_count": 1,
        "suspected_occluded": contribution_class == "zero_or_negligible_contribution",
        "region": {"x": 18, "y": 18, "width": 6, "height": 6},
        "global_metrics": {"global_changed_pixel_ratio": 0.0},
        "local_metrics": {"local_changed_pixel_ratio": 0.0},
    }


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
