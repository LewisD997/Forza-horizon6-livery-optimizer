import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.ablation_auto_triage import triage_ablation_result
from engine.visualization.ablation_evidence_pack import generate_ablation_evidence_pack
from scripts.validate_ablation_evidence_pack import validate_ablation_evidence_pack_report


def main():
    test_triage_rules()
    test_evidence_pack_outputs_and_validation()
    test_missing_candidate_images_warn_without_crash()
    print("Ablation evidence pack smoke test passed.")
    return 0


def test_triage_rules():
    assert _triage("completed", "safe_to_remove", 0.0001, 0.01, "tiny_fragment_cluster_member") == "safe_delete_candidate"
    assert _triage("completed", "risky", 0.0004, 0.05, "ellipse_cluster_member") == "unclear_needs_review"
    assert _triage("completed", "risky", 0.0008, 0.14, "low_alpha_large_soft_shape") == "needs_replacement"
    assert _triage("completed", "risky", 0.002, 0.36, "low_alpha_large_soft_shape") == "protect_candidate"
    assert _triage("missing_inputs", "failed", None, None, "fixture") == "unclear_needs_review"


def test_evidence_pack_outputs_and_validation():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        ablation = _write_fixture(root)
        original = json.dumps(ablation, sort_keys=True)
        report = generate_ablation_evidence_pack(
            ablation,
            str(root / "evidence_pack"),
            options={
                "source_ablation_report": root / "per_candidate_ablation_report.json",
                "crop_padding": 8,
                "upscale": 3,
                "amplify_diff": 5.0,
            },
        )
        validate_ablation_evidence_pack_report(report)
        assert report["status"] == "completed"
        assert report["candidate_count"] == 2
        assert (root / "evidence_pack" / "ablation_evidence_sheet.png").exists()
        assert (root / "evidence_pack" / "assistant_review_pack" / "assistant_review_manifest.json").exists()
        for candidate in report["candidates"]:
            outputs = candidate["outputs"]
            assert Path(outputs["before_crop"]).exists()
            assert Path(outputs["after_crop"]).exists()
            assert Path(outputs["amplified_diff_crop"]).exists()
            assert Path(outputs["review_card"]).exists()
        assert json.dumps(ablation, sort_keys=True) == original


def test_missing_candidate_images_warn_without_crash():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        ablation = {
            "results": [
                {
                    "change_id": "missing",
                    "shape_index": 1,
                    "candidate_type": "tiny_fragment_cluster_member",
                    "risk_level": "low",
                    "impact": {
                        "status": "completed",
                        "overall_decision": "safe_to_remove",
                        "changed_pixel_ratio": 0.0,
                        "mean_abs_diff": 0.0,
                        "local_changed_pixel_ratio": 0.0,
                    },
                    "outputs": {"before_preview": str(root / "missing_before.png")},
                }
            ]
        }
        report = generate_ablation_evidence_pack(ablation, str(root / "evidence_pack"))
        validate_ablation_evidence_pack_report(report)
        assert report["status"] == "completed_with_warnings"
        assert report["warnings"]
        assert report["candidates"][0]["triage_decision"] == "unclear_needs_review"


def _triage(status, decision, global_ratio, local_ratio, candidate_type):
    result = {
        "change_id": "fixture",
        "candidate_type": candidate_type,
        "impact": {
            "status": status,
            "overall_decision": decision,
            "changed_pixel_ratio": global_ratio,
            "local_changed_pixel_ratio": local_ratio,
        },
    }
    return triage_ablation_result(result)["triage_decision"]


def _write_fixture(root):
    from PIL import Image, ImageDraw, ImageChops

    candidates = []
    for index, change_id in enumerate(("C0001", "C0002"), start=1):
        cdir = root / "candidates" / change_id
        cdir.mkdir(parents=True)
        before = Image.new("RGBA", (80, 60), (255, 255, 255, 255))
        after = before.copy()
        draw = ImageDraw.Draw(after)
        if change_id == "C0001":
            draw.rectangle((20, 20, 22, 22), fill=(245, 245, 245, 255))
            local = 0.01
            global_ratio = 0.0001
            candidate_type = "tiny_fragment_cluster_member"
        else:
            draw.rectangle((36, 20, 50, 34), fill=(240, 80, 80, 255))
            local = 0.18
            global_ratio = 0.0015
            candidate_type = "low_alpha_large_soft_shape"
        before_path = cdir / "before_preview.png"
        after_path = cdir / "after_preview.png"
        diff_path = cdir / "diff.png"
        impact_path = cdir / "removal_impact_report.json"
        before.save(before_path)
        after.save(after_path)
        ImageChops.difference(before.convert("RGB"), after.convert("RGB")).save(diff_path)
        impact = {
            "global_metrics": {
                "changed_bbox": {"x": 18, "y": 18, "width": 36, "height": 22},
            },
            "per_removed_shape_metrics": [
                {"region": {"x": 16, "y": 16, "width": 40, "height": 26}}
            ],
        }
        impact_path.write_text(json.dumps(impact, indent=2), encoding="utf-8")
        candidates.append(
            {
                "change_id": change_id,
                "shape_index": index,
                "shape_uid": f"shape-{index}",
                "candidate_type": candidate_type,
                "risk_level": "low",
                "impact": {
                    "status": "completed",
                    "overall_decision": "safe_to_remove" if index == 1 else "risky",
                    "changed_pixel_ratio": global_ratio,
                    "mean_abs_diff": 0.00001,
                    "local_changed_pixel_ratio": local,
                },
                "outputs": {
                    "before_preview": str(before_path),
                    "after_preview": str(after_path),
                    "diff": str(diff_path),
                    "impact_report": str(impact_path),
                },
            }
        )
    ablation = {
        "ablation_version": "0.6.9",
        "status": "completed",
        "candidate_count": len(candidates),
        "results": candidates,
    }
    (root / "per_candidate_ablation_report.json").write_text(json.dumps(ablation, indent=2), encoding="utf-8")
    return ablation


if __name__ == "__main__":
    raise SystemExit(main())
