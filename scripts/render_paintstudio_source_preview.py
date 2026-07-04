import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview


def main():
    parser = argparse.ArgumentParser(
        description="Render a Paint Studio geometry.json preview using source-confirmed semantics."
    )
    parser.add_argument("--case", required=True, help="Case folder, for example cases/case_0001.")
    parser.add_argument("--ssaa", type=int, default=2, choices=(1, 2, 4), help="SSAA scale.")
    args = parser.parse_args()

    try:
        report = render_case(Path(args.case), args.ssaa)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Source-grounded preview written to {report['outputs']['preview']}")
    print(f"Report written to {report['outputs']['report']}")
    if report["comparisons"].get("paintstudio_preview", {}).get("available"):
        score = report["comparisons"]["paintstudio_preview"].get("difference_score")
        print(f"Paint Studio preview difference score: {score}")
    return 0


def render_case(case_dir: Path, ssaa: int) -> dict:
    geometry_path = case_dir / "paintstudio_geometry.json"
    source_path = case_dir / "source_full.png"
    paintstudio_preview_path = case_dir / "paintstudio_preview.png"
    output_dir = case_dir / "source_renderer"
    preview_path = output_dir / "paintstudio_source_renderer_preview.png"
    diff_path = output_dir / "paintstudio_source_renderer_diff.png"
    report_path = output_dir / "paintstudio_source_renderer_report.json"

    if not geometry_path.exists():
        raise FileNotFoundError(f"Missing geometry file: {geometry_path}")

    width = height = None
    if source_path.exists():
        from PIL import Image

        with Image.open(source_path) as image:
            width, height = image.size

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = render_paint_studio_preview(
        str(geometry_path),
        str(preview_path),
        width=width,
        height=height,
        ssaa=ssaa,
    )

    paintstudio_comparison = _compare(preview_path, paintstudio_preview_path, diff_path)
    source_comparison = _compare(preview_path, source_path, None)

    warnings = list(metadata.get("warnings", []))
    if source_path.exists() and paintstudio_preview_path.exists():
        source_size = _image_size(source_path)
        preview_size = _image_size(paintstudio_preview_path)
        if source_size != preview_size:
            warnings.append(
                "Paint Studio preview dimensions do not match source_full.png; comparison may be scaled."
            )

    report = {
        "case_dir": str(case_dir),
        "inputs": {
            "geometry": str(geometry_path),
            "source_full": str(source_path) if source_path.exists() else None,
            "paintstudio_preview": str(paintstudio_preview_path)
            if paintstudio_preview_path.exists()
            else None,
        },
        "outputs": {
            "preview": str(preview_path),
            "diff": str(diff_path) if diff_path.exists() else None,
            "report": str(report_path),
        },
        "render_metadata": metadata,
        "comparisons": {
            "paintstudio_preview": paintstudio_comparison,
            "source_full": source_comparison,
        },
        "warnings": warnings,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _compare(candidate_path, target_path, diff_path):
    if not target_path or not Path(target_path).exists():
        return {
            "available": False,
            "target_path": str(target_path) if target_path else None,
            "difference_score": None,
            "resized_for_score": False,
            "diff_path": None,
        }

    from PIL import Image, ImageChops

    with Image.open(candidate_path) as candidate_image:
        candidate = candidate_image.convert("RGB")
    with Image.open(target_path) as target_image:
        target = target_image.convert("RGB")

    candidate_size = candidate.size
    resized = candidate.size != target.size
    if resized:
        candidate = candidate.resize(target.size, Image.Resampling.BICUBIC)

    diff = ImageChops.difference(target, candidate)
    if diff_path:
        _make_visible_diff(diff).save(diff_path)

    return {
        "available": True,
        "target_path": str(target_path),
        "target_size": {"width": target.size[0], "height": target.size[1]},
        "candidate_size": {"width": candidate_size[0], "height": candidate_size[1]},
        "difference_score": _difference_score(diff),
        "resized_for_score": resized,
        "diff_path": str(diff_path) if diff_path else None,
    }


def _image_size(path):
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _difference_score(diff):
    pixel_count = diff.size[0] * diff.size[1]
    if pixel_count <= 0:
        return 0.0
    total = sum(diff.tobytes()) / (255 * 3)
    return round(total / pixel_count, 4)


def _make_visible_diff(diff):
    return diff.point(lambda value: min(255, value * 3))


if __name__ == "__main__":
    raise SystemExit(main())
