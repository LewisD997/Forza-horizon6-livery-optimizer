import argparse
import sys
from pathlib import Path

from engine.analyzer.layer_analyzer import analyze_layers
from engine.parser.jsdn_parser import JsdnParseError, parse_jsdn
from engine.renderer.preview_renderer import render_preview_placeholder
from engine.reports.report_writer import write_report
from engine.vision.image_inspector import inspect_reference_image


def build_report(image_path, input_path):
    layers = parse_jsdn(input_path)
    image_info = inspect_reference_image(image_path)
    analysis = analyze_layers(layers, image_info)
    render_preview_placeholder(layers, image_info)

    return {
        "total_layers": len(layers),
        "image_info": image_info,
        "issues": analysis["issues"],
        "suspected_messy_regions": analysis["suspected_messy_regions"],
        "estimated_removable_layers": analysis["estimated_removable_layers"],
        "notes": analysis["notes"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="FLO analyzes generated Forza livery files against an original image target."
    )
    parser.add_argument("--image", required=True, help="Path to the original reference image.")
    parser.add_argument("--input", required=True, help="Path to the generated .jsdn livery file.")
    parser.add_argument("--report", required=True, help="Path to the JSON report output.")
    args = parser.parse_args()

    image_path = Path(args.image)
    input_path = Path(args.input)
    report_path = Path(args.report)

    try:
        report = build_report(image_path, input_path)
    except (JsdnParseError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_report(report, report_path)
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
