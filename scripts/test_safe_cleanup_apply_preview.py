import copy
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from engine.optimizer.change_plan import make_shape_uid
from engine.optimizer.safe_cleanup_preview_applier import apply_safe_cleanup_preview, reconstruct_original_from_preview
from engine.output.safe_cleanup_preview_writer import SafeCleanupPreviewWriteError, write_preview_cleanup_geometry
from scripts.apply_safe_cleanup_preview import run_from_args
from scripts.validate_safe_cleanup_apply_preview import validate_safe_cleanup_apply_preview


def main():
    test_valid_apply_and_exact_rollback(); test_identity_feedback_and_group_blocks()
    test_duplicates_and_multiple_order(); test_writer_guards(); test_cli_and_validator()
    print("Safe cleanup apply preview tests passed."); return 0


def test_valid_apply_and_exact_rollback():
    geometry = _geometry(); original = copy.deepcopy(geometry)
    result = apply_safe_cleanup_preview(geometry, _proposal(geometry, [("C1", 1)]), _visible(geometry, [("C1", 1)]), {"items": []})
    assert result["status"] == "completed" and result["output_shape_count"] == 3 and geometry == original
    assert reconstruct_original_from_preview(result["preview_geometry"], result["application_ledger"]) == original
    assert result["application_ledger"][0]["rollback_payload"]["shape"]["custom"] == {"keep": True}


def test_identity_feedback_and_group_blocks():
    geometry = _geometry(); bad = _proposal(geometry, [("C1", 1)]); bad["proposed_removals"][0]["shape_uid"] = "wrong"
    assert apply_safe_cleanup_preview(geometry, bad, _visible(geometry, [("C1", 1)]))["applied_removal_count"] == 0
    feedback = {"items": [{"change_id": "C1", "status": "rejected"}]}
    assert apply_safe_cleanup_preview(geometry, _proposal(geometry, [("C1", 1)]), _visible(geometry, [("C1", 1)]), feedback)["applied_removal_count"] == 0
    visible = _visible(geometry, [("C1", 1)]); visible["summary"]["replacement_candidate"] = ["C1"]
    assert apply_safe_cleanup_preview(geometry, _proposal(geometry, [("C1", 1)]), visible)["applied_removal_count"] == 0


def test_duplicates_and_multiple_order():
    geometry = _geometry(); entries = [("C1", 1), ("C1_DUP", 1), ("C3", 3)]
    result = apply_safe_cleanup_preview(geometry, _proposal(geometry, entries), _visible(geometry, entries))
    assert result["applied_removal_count"] == 2 and result["skipped_removal_count"] == 1
    assert [shape["data"][0] for shape in result["preview_geometry"]["shapes"]] == [0, 20]
    assert [item["original_shape_index"] for item in result["application_ledger"]] == [3, 1]
    assert reconstruct_original_from_preview(result["preview_geometry"], result["application_ledger"]) == geometry


def test_writer_guards():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); original = root / "geometry.json"; original.write_text("{}", encoding="utf-8")
        for path in (original, root / "optimized_geometry.json"):
            try: write_preview_cleanup_geometry(_geometry(), path, original_input_path=original)
            except SafeCleanupPreviewWriteError: pass
            else: raise AssertionError("Writer accepted a forbidden output path.")


def test_cli_and_validator():
    with tempfile.TemporaryDirectory() as temp:
        case = Path(temp) / "case"; (case / "safe_delete_validation").mkdir(parents=True); (case / "visible_contribution").mkdir(); (case / "candidate_review").mkdir()
        geometry = _geometry(); _write(case / "paintstudio_geometry.json", geometry)
        _write(case / "safe_delete_validation" / "safe_delete_cleanup_proposal.json", _proposal(geometry, [("C1", 1)]))
        _write(case / "visible_contribution" / "visible_contribution_report.json", _visible(geometry, [("C1", 1)]))
        _write(case / "candidate_review" / "candidate_feedback.json", {"items": []})
        args = SimpleNamespace(case=str(case), geometry=None, proposal=None, visible_report=None, feedback=None, source_image=None,
            output_dir=None, overwrite=False, no_render=True, preview_renderer="paintstudio-source", max_removals=None,
            write_rollback_preview=True, skip_reference_comparison=False)
        report = run_from_args(args); validate_safe_cleanup_apply_preview(report, geometry)
        assert report["reference_comparison"]["status"] == "not_available"


def _geometry():
    return {"canvas": {"note": "preserve"}, "shapes": [
        {"type": 1, "data": [0, 0, 40, 30], "color": [255, 255, 255, 255], "score": 0},
        {"type": 16, "data": [10, 10, 1, 1, 0, 0], "color": [255, 0, 0, 0], "score": .1, "locked": False, "custom": {"keep": True}},
        {"type": 2, "data": [20, 15, 3, 2, 0, 0], "color": [0, 0, 0, 255], "score": .5},
        {"type": 32, "data": [1, 1, 3, 1, 2, 3], "color": [0, 0, 0, 0], "score": .2}]}


def _proposal(geometry, entries):
    return {"cleanup_proposal_version": "0.6.12", "proposal_type": "safe_delete_pool", "status": "proposed", "official_geometry_written": False,
        "proposed_removals": [{"change_id": cid, "shape_index": index, "shape_uid": make_shape_uid(geometry["shapes"][index], index),
            "reason": "zero_or_negligible_visible_contribution", "requires_final_apply": True} for cid, index in entries]}


def _visible(geometry, entries):
    return {"results": [{"change_id": cid, "shape_index": index, "shape_uid": make_shape_uid(geometry["shapes"][index], index),
        "contribution_class": "zero_or_negligible_contribution", "recommended_action": "safe_delete_pool"} for cid, index in entries],
        "summary": {"protect_candidate": [], "replacement_candidate": [], "deletion_candidate_review": []}}


def _write(path, data): path.write_text(json.dumps(data, indent=2), encoding="utf-8")
if __name__ == "__main__": raise SystemExit(main())
