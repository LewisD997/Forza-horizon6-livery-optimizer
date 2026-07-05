import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_feedback import create_feedback_template, update_feedback_status
from engine.optimizer.candidate_planner import generate_cleanup_candidate_plan
from scripts.render_candidate_review import render_review


def main():
    geometry = _fixture_geometry()
    original = json.loads(json.dumps(geometry))
    plan = generate_cleanup_candidate_plan(
        geometry,
        {"image_info": {"size": {"width": 200, "height": 160}}},
        options={"input_geometry_path": "fixture.json", "max_candidates": 10},
    )
    assert plan["proposed_change_count"] >= 4

    feedback = create_feedback_template(plan)
    feedback = update_feedback_status(feedback, feedback["items"][0]["change_id"], "accepted", "Looks safe.")
    feedback = update_feedback_status(feedback, feedback["items"][1]["change_id"], "rejected", "Keep this detail.")
    feedback = update_feedback_status(feedback, feedback["items"][2]["change_id"], "protected", "Must not touch.")
    feedback = update_feedback_status(feedback, feedback["items"][3]["change_id"], "unsure", "Review later.")
    feedback["items"].append(
        {
            "change_id": "C9999",
            "shape_index": 9999,
            "shape_uid": "unknown",
            "candidate_type": "unknown_review_candidate",
            "status": "unsure",
            "reviewer_note": "Mismatch warning fixture.",
            "reviewed_at": None,
            "metadata": {},
        }
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        plan_path = temp / "optimization_plan.json"
        geometry_path = temp / "paintstudio_geometry.json"
        base_path = temp / "base.png"
        feedback_path = temp / "candidate_feedback.json"
        output_dir = temp / "candidate_review"
        _write_json(plan_path, plan)
        _write_json(geometry_path, geometry)
        _write_json(feedback_path, feedback)
        _write_base_image(base_path)

        report = render_review(
            _args(
                plan=plan_path,
                geometry=geometry_path,
                base_image=base_path,
                output_dir=output_dir,
                feedback=feedback_path,
                show_feedback=True,
            )
        )
        assert (output_dir / "candidate_overlay_feedback_all.png").exists()
        assert (output_dir / "candidate_overlay_feedback_accepted.png").exists()
        assert (output_dir / "candidate_overlay_feedback_rejected.png").exists()
        assert (output_dir / "candidate_overlay_feedback_protected.png").exists()
        assert (output_dir / "candidate_overlay_feedback_unsure.png").exists()
        assert (output_dir / "candidate_contact_sheet_feedback_all.png").exists()
        assert (output_dir / "candidate_contact_sheet_feedback_protected.png").exists()
        assert (output_dir / "candidate_review_feedback_table.csv").exists()
        assert any("C9999" in warning for warning in report["warnings"])

        index = json.loads((output_dir / "candidate_review_index.json").read_text(encoding="utf-8"))
        assert index["feedback_available"] is True
        assert index["feedback_counts_by_status"]["protected"] == 1
        assert "outputs_by_feedback_status" in index

        filtered_dir = temp / "candidate_review_filtered"
        filtered = render_review(
            _args(
                plan=plan_path,
                geometry=geometry_path,
                base_image=base_path,
                output_dir=filtered_dir,
                feedback=feedback_path,
                feedback_status="protected",
            )
        )
        assert (filtered_dir / "candidate_overlay_feedback_protected.png").exists()
        protected_outputs = filtered["index"]["outputs_by_feedback_status"]["protected"]
        assert protected_outputs["overlay_rendered_candidates"] == 1

        fallback_dir = temp / "candidate_review_fallback"
        fallback = render_review(
            _args(
                plan=plan_path,
                geometry=geometry_path,
                base_image=base_path,
                output_dir=fallback_dir,
                feedback=temp / "missing_feedback.json",
                show_feedback=True,
            )
        )
        assert (fallback_dir / "candidate_overlay_all.png").exists()
        assert fallback["index"]["feedback_available"] is False
        assert any("Feedback file not found" in warning for warning in fallback["warnings"])

    assert geometry == original
    print("Feedback-aware review visualization smoke test passed.")
    return 0


def _args(**kwargs):
    defaults = {
        "case": None,
        "plan": None,
        "geometry": None,
        "base_image": None,
        "output_dir": None,
        "top_n": 50,
        "candidate_type": None,
        "risk_level": None,
        "feedback": None,
        "feedback_status": None,
        "show_feedback": False,
        "hide_feedback": False,
        "crop_padding": 24,
        "no_crops": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**{key: str(value) if isinstance(value, Path) else value for key, value in defaults.items()})


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_base_image(path):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (200, 160), (245, 245, 245, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 180, 140), fill=(220, 220, 240, 255))
    image.save(path)


def _fixture_geometry():
    return {
        "shapes": [
            {"type": 1, "data": [0, 0, 200, 160], "color": [245, 245, 245, 255], "score": 0},
            {"type": 16, "data": [54, 44, 26, 18, 0, 0], "color": [120, 120, 255, 80], "score": 0.7},
            {"type": 16, "data": [86, 44, 14, 10, 0, 0], "color": [120, 120, 255, 90], "score": 0.6},
            {"type": 16, "data": [118, 44, 12, 9, 0, 0], "color": [120, 120, 255, 100], "score": 0.6},
            {"type": 16, "data": [150, 44, 11, 9, 0, 0], "color": [120, 120, 255, 100], "score": 0.6},
            {"type": 1, "data": [40, 110, 8, 6], "color": [245, 245, 245, 255], "score": 0.4},
            {"type": 1, "data": [40, 110, 8, 6], "color": [245, 245, 245, 255], "score": 0.4},
        ]
    }


if __name__ == "__main__":
    raise SystemExit(main())
