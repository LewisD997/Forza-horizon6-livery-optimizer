import argparse
import sys
from pathlib import Path

from engine.analyzer.layer_analyzer import analyze_layers, score_layers
from engine.optimizer.suggestion_engine import (
    generate_optimization_suggestions,
    summarize_suggestions,
)
from engine.parser.jsdn_parser import JsdnParseError, parse_jsdn
from engine.renderer.preview_renderer import PreviewRenderError, render_preview
from engine.reports.training_case_logger import write_training_cases
from engine.reports.report_writer import write_report
from engine.knowledge.primitive_kb import is_known_primitive
from engine.vision.image_inspector import inspect_reference_image
from engine.vision.visual_diff import VisualDiffError, compare_images


def build_report(image_path, input_path, preview_path=None, diff_path=None):
    layers = parse_jsdn(input_path)
    image_info = inspect_reference_image(image_path)
    analysis = analyze_layers(layers, image_info)
    scores = score_layers(layers, analysis)
    notes = list(analysis["notes"])
    rendered_preview_path = None
    visual_diff = None

    if preview_path:
        preview_result = render_preview(layers, image_info, preview_path)
        rendered_preview_path = preview_result["preview_path"]
        notes.extend(preview_result["notes"])

    if diff_path:
        if not rendered_preview_path:
            raise ValueError("--diff requires --preview so FLO has a rendered livery image to compare.")
        visual_diff = compare_images(image_path, rendered_preview_path, diff_path)

    suggestions = generate_optimization_suggestions(
        layers,
        analysis["issues"],
        visual_diff=visual_diff,
    )

    return {
        "total_layers": len(layers),
        "image_info": image_info,
        "preview_path": rendered_preview_path,
        "visual_diff": visual_diff,
        "scores": scores,
        "unknown_primitives": _unknown_primitives(layers),
        "optimization_suggestions": suggestions,
        "suggestion_summary": summarize_suggestions(suggestions),
        "issues": analysis["issues"],
        "suspected_messy_regions": analysis["suspected_messy_regions"],
        "estimated_removable_layers": analysis["estimated_removable_layers"],
        "notes": notes,
    }


def _unknown_primitives(layers):
    unknown = sorted(
        {
            str(layer["shape"])
            for layer in layers
            if not is_known_primitive(layer["shape"])
        }
    )
    return unknown


def main():
    parser = argparse.ArgumentParser(
        description="FLO analyzes generated Forza livery files against an original image target."
    )
    parser.add_argument("--image", required=True, help="Path to the original reference image.")
    parser.add_argument("--input", required=True, help="Path to the generated .jsdn livery file.")
    parser.add_argument("--report", required=True, help="Path to the JSON report output.")
    parser.add_argument("--preview", help="Optional path to write a rendered PNG preview.")
    parser.add_argument("--diff", help="Optional path to write a PNG visual diff.")
    parser.add_argument(
        "--log-training-cases",
        action="store_true",
        help="Write pending suggestion cases to database/training_cases.jsonl.",
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    input_path = Path(args.input)
    report_path = Path(args.report)
    preview_path = Path(args.preview) if args.preview else None
    diff_path = Path(args.diff) if args.diff else None

    try:
        report = build_report(image_path, input_path, preview_path, diff_path)
    except (JsdnParseError, PreviewRenderError, VisualDiffError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_report(report, report_path)
    print(f"Report written to {report_path}")
    if preview_path:
        print(f"Preview written to {preview_path}")
    if diff_path:
        print(f"Diff written to {diff_path}")
    if args.log_training_cases:
        case_path = write_training_cases(
            image_path,
            input_path,
            report["optimization_suggestions"],
        )
        print(f"Training cases written to {case_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
