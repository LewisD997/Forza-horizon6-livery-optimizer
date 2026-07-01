import argparse
import sys
from pathlib import Path

from engine.analyzer.layer_analyzer import analyze_layers
from engine.parser.jsdn_parser import JsdnParseError, parse_jsdn
from engine.renderer.preview_renderer import PreviewRenderError, render_preview
from engine.reports.report_writer import write_report
from engine.vision.image_inspector import inspect_reference_image


def build_report(image_path, input_path, preview_path=None):
    layers = parse_jsdn(input_path)
    image_info = inspect_reference_image(image_path)
    analysis = analyze_layers(layers, image_info)
    notes = list(analysis["notes"])
    rendered_preview_path = None

    if preview_path:
        preview_result = render_preview(layers, image_info, preview_path)
        rendered_preview_path = preview_result["preview_path"]
        notes.extend(preview_result["notes"])

    return {
        "total_layers": len(layers),
        "image_info": image_info,
        "preview_path": rendered_preview_path,
        "issues": analysis["issues"],
        "suspected_messy_regions": analysis["suspected_messy_regions"],
        "estimated_removable_layers": analysis["estimated_removable_layers"],
        "notes": notes,
    }


def main():
    parser = argparse.ArgumentParser(
        description="FLO analyzes generated Forza livery files against an original image target."
    )
    parser.add_argument("--image", required=True, help="Path to the original reference image.")
    parser.add_argument("--input", required=True, help="Path to the generated .jsdn livery file.")
    parser.add_argument("--report", required=True, help="Path to the JSON report output.")
    parser.add_argument("--preview", help="Optional path to write a rendered PNG preview.")
    args = parser.parse_args()

    image_path = Path(args.image)
    input_path = Path(args.input)
    report_path = Path(args.report)
    preview_path = Path(args.preview) if args.preview else None

    try:
        report = build_report(image_path, input_path, preview_path)
    except (JsdnParseError, PreviewRenderError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_report(report, report_path)
    print(f"Report written to {report_path}")
    if preview_path:
        print(f"Preview written to {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
