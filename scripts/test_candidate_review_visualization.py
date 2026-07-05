import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_planner import generate_cleanup_candidate_plan
from engine.visualization.candidate_review_visualizer import (
    export_candidate_crops,
    render_candidate_contact_sheet,
    render_candidate_overlay,
    write_candidate_review_index,
)


def main():
    from PIL import Image, ImageDraw

    geometry = _fixture_geometry()
    original = json.loads(json.dumps(geometry))
    plan = generate_cleanup_candidate_plan(
        geometry,
        {"image_info": {"size": {"width": 200, "height": 160}}},
        options={"input_geometry_path": "fixture.json", "max_candidates": 10},
    )
    assert plan["proposed_change_count"] > 0

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        base_path = temp / "base.png"
        base = Image.new("RGBA", (200, 160), (245, 245, 245, 255))
        draw = ImageDraw.Draw(base)
        draw.rectangle((20, 20, 180, 140), fill=(220, 220, 240, 255))
        base.save(base_path)

        overlay = render_candidate_overlay(str(base_path), plan, geometry, str(temp / "overlay.png"))
        assert Path(overlay["output_path"]).exists()
        assert overlay["rendered_candidates"] > 0

        sheet = render_candidate_contact_sheet(str(base_path), plan, geometry, str(temp / "sheet.png"))
        assert Path(sheet["output_path"]).exists()
        assert sheet["rendered_candidates"] > 0

        filtered = render_candidate_contact_sheet(
            str(base_path),
            plan,
            geometry,
            str(temp / "sheet_low_alpha.png"),
            {"candidate_type": "low_alpha_large_soft_shape"},
        )
        assert Path(filtered["output_path"]).exists()

        crops = export_candidate_crops(str(base_path), plan, geometry, str(temp / "crops"))
        assert crops["rendered_candidates"] > 0
        assert Path(crops["crop_paths"][0]).exists()

        index = write_candidate_review_index(
            plan,
            temp / "candidate_review_index.json",
            {"rendered_candidates": overlay["rendered_candidates"], "skipped_candidates": 0},
        )
        assert index["total_candidates"] == plan["proposed_change_count"]
        assert Path(temp / "candidate_review_index.json").exists()

    assert geometry == original
    print("Candidate review visualization smoke test passed.")
    return 0


def _fixture_geometry():
    return {
        "shapes": [
            {"type": 1, "data": [0, 0, 200, 160], "color": [245, 245, 245, 255], "score": 0},
            {"type": 16, "data": [54, 44, 26, 18, 0, 0], "color": [120, 120, 255, 80], "score": 0.7},
            {"type": 16, "data": [110, 70, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
            {"type": 16, "data": [114, 72, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
            {"type": 16, "data": [118, 74, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
            {"type": 16, "data": [122, 76, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
            {"type": 16, "data": [126, 78, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
        ]
    }


if __name__ == "__main__":
    raise SystemExit(main())
