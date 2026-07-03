import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.diagnostics.paint_studio_renderer_diagnostic import diagnose_paint_studio_geometry


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose FLO preview renderer compatibility with Paint Studio geometry."
    )
    parser.add_argument("--case", required=True, help="Case folder, for example cases/case_0001.")
    args = parser.parse_args()

    case_dir = Path(args.case)
    geometry_path = case_dir / "paintstudio_geometry.json"
    source_path = case_dir / "source_full.png"
    paintstudio_preview_path = case_dir / "paintstudio_preview.png"
    output_dir = case_dir / "renderer_diagnostic"

    missing = [path for path in (geometry_path, source_path, paintstudio_preview_path) if not path.exists()]
    if missing:
        print("Missing required case files:")
        for path in missing:
            print(f"- {path}")
        return 1

    report = diagnose_paint_studio_geometry(
        str(geometry_path),
        source_image_path=str(source_path),
        paintstudio_preview_path=str(paintstudio_preview_path),
        output_dir=str(output_dir),
    )

    closest = report["comparisons"].get("closest_to_paintstudio_preview")
    warning = report.get("renderer_compatibility_warning", {})

    print(f"Renderer diagnostic written to {output_dir}")
    print(f"Total shapes: {report['shape_diagnostics']['total_shape_count']}")
    print(f"Unknown/mask-like types: {report['shape_diagnostics']['mask_like_type_count']}")
    if closest:
        print(
            "Closest to Paint Studio preview: "
            f"{closest['variant']} ({closest['difference_score']})"
        )
    print(f"Renderer compatibility warning: {json.dumps(warning)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
