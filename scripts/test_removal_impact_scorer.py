import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.removal_impact_scorer import score_removal_impact
from engine.output.removal_impact_writer import validate_removal_impact_report


def main():
    test_no_removals_missing_after()
    test_identical_before_after()
    test_tiny_difference()
    test_large_difference()
    test_size_mismatch()
    test_per_removed_shape_local_metrics()
    print("Removal impact scorer smoke test passed.")
    return 0


def test_no_removals_missing_after():
    report = score_removal_impact(
        "missing_before.png",
        "missing_after.png",
        removal_report=_removal_report(removed_count=0),
    )
    assert report["status"] == "not_applicable_no_removals"
    assert report["overall_decision"] == "not_applicable"
    validate_removal_impact_report(report)


def test_identical_before_after():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        before = temp / "before.png"
        after = temp / "after.png"
        _write_image(before)
        _write_image(after)
        report = score_removal_impact(str(before), str(after), removal_report=_removal_report())
        assert report["status"] == "completed"
        assert report["overall_decision"] == "safe_to_remove"
        assert report["global_metrics"]["changed_pixel_ratio"] == 0
        validate_removal_impact_report(report)


def test_tiny_difference():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        before = temp / "before.png"
        after = temp / "after.png"
        _write_image(before)
        _write_image(after, points=[(1, 1, (252, 252, 252, 255))])
        report = score_removal_impact(str(before), str(after), removal_report=_removal_report())
        assert report["status"] == "completed"
        assert report["overall_decision"] in {"safe_to_remove", "probably_safe"}
        assert report["global_metrics"]["changed_pixel_ratio"] > 0
        validate_removal_impact_report(report)


def test_large_difference():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        before = temp / "before.png"
        after = temp / "after.png"
        _write_image(before)
        _write_image(after, rect=(0, 0, 20, 20, (0, 0, 0, 255)))
        report = score_removal_impact(str(before), str(after), removal_report=_removal_report())
        assert report["status"] == "completed"
        assert report["overall_decision"] == "risky"
        validate_removal_impact_report(report)


def test_size_mismatch():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        before = temp / "before.png"
        after = temp / "after.png"
        _write_image(before, size=(20, 20))
        _write_image(after, size=(10, 10))
        report = score_removal_impact(str(before), str(after), removal_report=_removal_report())
        assert report["status"] == "failed"
        assert report["overall_decision"] == "failed"
        assert report["warnings"]
        validate_removal_impact_report(report)


def test_per_removed_shape_local_metrics():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        before = temp / "before.png"
        after = temp / "after.png"
        _write_image(before)
        _write_image(after, rect=(5, 5, 9, 9, (0, 0, 0, 255)))
        report = score_removal_impact(
            str(before),
            str(after),
            removal_report=_removal_report(),
            plan=_plan(),
            feedback=_feedback(),
            options={"local_padding": 0},
        )
        assert report["per_removed_shape_metrics"]
        local = report["per_removed_shape_metrics"][0]
        assert local["change_id"] == "C0001"
        assert local["local_changed_pixel_ratio"] > 0
        assert local["region"]["x"] == 5
        validate_removal_impact_report(report)


def _write_image(path, size=(20, 20), points=None, rect=None):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", size, (255, 255, 255, 255))
    if rect:
        x0, y0, x1, y1, color = rect
        ImageDraw.Draw(image).rectangle((x0, y0, x1, y1), fill=color)
    for x, y, color in points or []:
        image.putpixel((x, y), color)
    image.save(path)


def _removal_report(removed_count=1):
    return {
        "input_shape_count": 4,
        "output_shape_count": 4 - removed_count,
        "simulated_removed_count": removed_count,
        "removed_shapes": [
            {
                "change_id": "C0001",
                "shape_index": 1,
                "shape_uid": "shape-1",
                "feedback_status": "accepted",
                "candidate_type": "fixture_candidate",
                "shape": {"type": 1, "data": [5, 5, 4, 4], "color": [0, 0, 0, 255]},
            }
        ]
        if removed_count
        else [],
    }


def _plan():
    return {
        "changes": [
            {
                "change_id": "C0001",
                "shape_index": 1,
                "shape_uid": "shape-1",
                "risk_level": "low",
                "metadata": {
                    "candidate_type": "fixture_candidate",
                    "region": {"x": 5, "y": 5, "width": 5, "height": 5},
                },
            }
        ]
    }


def _feedback():
    return {
        "items": [
            {
                "change_id": "C0001",
                "status": "accepted",
                "shape_uid": "shape-1",
            }
        ]
    }


if __name__ == "__main__":
    raise SystemExit(main())
