import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.renderer.export_alignment import compare_images, crop_to_bbox, get_alpha_bbox
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview


def main():
    from PIL import Image, ImageDraw

    fixture = ROOT / "test_data" / "paint_studio_source_renderer_fixture.json"
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        sample = Image.new("RGBA", (32, 24), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sample)
        draw.rectangle((10, 6, 19, 15), fill=(255, 0, 0, 255))
        bbox = get_alpha_bbox(sample)
        assert bbox == (10, 6, 20, 16)
        assert crop_to_bbox(sample, bbox).size == (10, 10)
        assert crop_to_bbox(sample, bbox, padding=2).size == (14, 14)

        target = temp / "target.png"
        candidate = temp / "candidate.png"
        diff_dir = temp / "diffs"
        sample.save(target)
        sample.save(candidate)
        comparison = compare_images(candidate, target, diff_dir=diff_dir, prefix="same", make_side_by_side=True)
        assert comparison["difference_score"] == 0.0
        assert comparison["dimensions_match"] is True
        assert (diff_dir / "same_abs_grayscale.png").exists()
        assert (diff_dir / "same_heatmap.png").exists()
        assert (diff_dir / "same_alpha.png").exists()
        assert (diff_dir / "same_overlay.png").exists()
        assert (diff_dir / "same_side_by_side.png").exists()

        full = temp / "full.png"
        transparent = temp / "transparent.png"
        cropped = temp / "cropped.png"
        padded = temp / "padded.png"
        meta_full = render_paint_studio_preview(str(fixture), str(full), ssaa=2)
        meta_transparent = render_paint_studio_preview(
            str(fixture),
            str(transparent),
            ssaa=2,
            export_mode="full_canvas_transparent",
        )
        meta_cropped = render_paint_studio_preview(
            str(fixture),
            str(cropped),
            ssaa=2,
            export_mode="cropped_transparent",
        )
        meta_padded = render_paint_studio_preview(
            str(fixture),
            str(padded),
            ssaa=2,
            export_mode="cropped_transparent_with_padding",
            padding=8,
        )
        assert meta_full["output_size"] == {"width": 160, "height": 120}
        assert meta_transparent["output_size"] == {"width": 160, "height": 120}
        assert meta_cropped["output_size"]["width"] < 160
        assert meta_cropped["output_size"]["height"] < 120
        assert meta_padded["output_size"]["width"] >= meta_cropped["output_size"]["width"]
        assert meta_padded["output_size"]["height"] >= meta_cropped["output_size"]["height"]

    print("Paint Studio export alignment smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
