import argparse
import json
import sys
from pathlib import Path

from engine.analyzer.anime_artifact_analyzer import analyze_anime_artifacts
from engine.analyzer.layer_analyzer import analyze_layers, score_layers
from engine.optimizer.suggestion_engine import (
    generate_optimization_suggestions,
    summarize_suggestions,
)
from engine.optimizer.geometry_optimizer import optimize_geometry_noop
from engine.optimizer.patch_applier import apply_optimization_plan
from engine.optimizer.plan_generator import generate_noop_plan
from engine.output.optimized_geometry_writer import (
    OptimizedGeometryWriteError,
    write_optimized_geometry,
)
from engine.output.optimization_plan_writer import (
    OptimizationPlanError,
    read_optimization_plan,
    validate_optimization_plan,
    write_optimization_plan,
)
from engine.parser.jsdn_parser import JsdnParseError, parse_jsdn
from engine.parser.paint_studio_geometry_parser import (
    PaintStudioGeometryParseError,
    looks_like_paint_studio_geometry,
    parse_paint_studio_geometry,
)
from engine.renderer.preview_renderer import PreviewRenderError, render_preview
from engine.renderer.paint_studio_source_renderer import (
    PaintStudioSourceRenderError,
    render_paint_studio_preview,
)
from engine.reports.training_case_logger import write_training_cases
from engine.reports.report_writer import write_report
from engine.knowledge.primitive_kb import is_known_primitive
from engine.vision.image_inspector import inspect_reference_image
from engine.vision.visual_diff import VisualDiffError, compare_images


def build_report(
    image_path,
    input_path,
    preview_path=None,
    diff_path=None,
    input_format="auto",
    preview_renderer="default",
):
    layers, resolved_input_format = parse_input_layers(input_path, input_format)
    image_info = inspect_reference_image(image_path)
    analysis = analyze_layers(layers, image_info)
    scores = score_layers(layers, analysis)
    notes = list(analysis["notes"])
    rendered_preview_path = None
    visual_diff = None

    if preview_path:
        preview_result = render_livery_preview(
            layers,
            image_info,
            preview_path,
            input_path,
            resolved_input_format,
            preview_renderer,
        )
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
    anime_artifact_analysis = analyze_anime_artifacts(
        layers,
        image_info=image_info,
        visual_diff=visual_diff,
    )

    return {
        "total_layers": len(layers),
        "input_format": resolved_input_format,
        "image_info": image_info,
        "preview_path": rendered_preview_path,
        "visual_diff": visual_diff,
        "scores": scores,
        "unknown_primitives": _unknown_primitives(layers),
        "anime_artifact_analysis": anime_artifact_analysis,
        "optimization_suggestions": suggestions,
        "suggestion_summary": summarize_suggestions(suggestions),
        "issues": analysis["issues"],
        "suspected_messy_regions": analysis["suspected_messy_regions"],
        "estimated_removable_layers": analysis["estimated_removable_layers"],
        "notes": notes,
    }


def render_livery_preview(
    layers,
    image_info,
    preview_path,
    input_path,
    resolved_input_format,
    preview_renderer="default",
):
    if preview_renderer == "default":
        return render_preview(layers, image_info, preview_path)
    if preview_renderer != "paintstudio-source":
        raise ValueError("--preview-renderer must be default or paintstudio-source.")
    if resolved_input_format != "paintstudio_geometry":
        raise ValueError("--preview-renderer paintstudio-source requires Paint Studio geometry input.")
    result = render_paint_studio_preview(
        str(input_path),
        str(preview_path),
        export_mode="full_canvas_opaque",
    )
    return {
        "preview_path": result["output_path"],
        "notes": [
            "Preview rendered with source-grounded Paint Studio renderer.",
            *[f"Paint Studio source renderer warning: {warning}" for warning in result.get("warnings", [])],
        ],
        "metadata": result,
    }


def parse_input_layers(input_path, input_format="auto"):
    requested_format = (input_format or "auto").lower()
    if requested_format == "jsdn":
        return parse_jsdn(input_path), "jsdn"
    if requested_format == "paintstudio":
        return parse_paint_studio_geometry(input_path), "paintstudio_geometry"
    if requested_format != "auto":
        raise ValueError("--input-format must be auto, jsdn, or paintstudio.")

    if _looks_like_paint_studio_file(input_path):
        return parse_paint_studio_geometry(input_path), "paintstudio_geometry"
    return parse_jsdn(input_path), "jsdn"


def _looks_like_paint_studio_file(input_path):
    source_path = Path(input_path)
    if source_path.name.lower() == "geometry.json":
        return True
    if source_path.suffix.lower() != ".json":
        return False
    try:
        import json

        data = json.loads(source_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return False
    return looks_like_paint_studio_geometry(data)


def _unknown_primitives(layers):
    unknown = sorted(
        {
            str(layer["shape"])
            for layer in layers
            if not is_known_primitive(layer["shape"])
        }
    )
    return unknown


def run_geometry_output_pipeline(
    input_path,
    image_path,
    output_geometry_path,
    optimization_mode,
    overwrite_output=False,
    after_preview_path=None,
    after_diff_path=None,
    preview_renderer="default",
):
    if optimization_mode != "noop":
        raise ValueError("--optimization-mode only supports noop in v0.6.0.")

    geometry = _read_paintstudio_geometry(input_path)
    optimization_result = optimize_geometry_noop(geometry)
    optimized_geometry = optimization_result["geometry"]
    optimizer_report = optimization_result["report"]
    preview_paths = {}
    renderer_used = preview_renderer

    write_report_metadata = {
        "optimization_mode": optimization_mode,
        "safety_level": "safe",
        "optimizer_report": optimizer_report,
        "renderer_used": renderer_used,
        "preview_paths": preview_paths,
        "tool_version": "v0.6.0",
    }

    output_report = write_optimized_geometry(
        str(input_path),
        str(output_geometry_path),
        shapes=optimized_geometry.get("shapes"),
        metadata=write_report_metadata,
        overwrite=overwrite_output,
    )

    if after_preview_path:
        if preview_renderer != "paintstudio-source":
            raise ValueError("v0.6.0 after-preview currently requires --preview-renderer paintstudio-source.")
        render_result = render_paint_studio_preview(
            str(output_geometry_path),
            str(after_preview_path),
            width=_image_width(image_path),
            height=_image_height(image_path),
            export_mode="full_canvas_opaque",
        )
        preview_paths["after_preview"] = render_result["output_path"]

    if after_diff_path:
        if not after_preview_path:
            raise ValueError("--after-diff requires --after-preview.")
        after_diff = compare_images(image_path, after_preview_path, after_diff_path)
        preview_paths["after_diff"] = after_diff["diff_path"]
        output_report["after_visual_diff"] = after_diff

    if preview_paths:
        output_report["preview_paths"] = preview_paths
        report_path = Path(output_geometry_path).with_name(
            f"{Path(output_geometry_path).stem}_optimization_report.json"
        )
        write_report(output_report, report_path)
    return output_report


def run_plan_pipeline(
    input_path,
    output_geometry_path=None,
    plan_output_path=None,
    plan_input_path=None,
    apply_plan=False,
    dry_run_plan=False,
    include_mark_candidates=False,
    overwrite_output=False,
):
    geometry = _read_paintstudio_geometry(input_path)
    result = {
        "generated_plan_path": None,
        "loaded_plan_path": None,
        "proposed_change_count": 0,
        "applied_change_count": 0,
        "dry_run": bool(dry_run_plan),
        "ledger": [],
        "warnings": [],
    }

    plan = None
    if plan_output_path:
        plan = generate_noop_plan(
            geometry,
            str(input_path),
            str(output_geometry_path) if output_geometry_path else None,
            include_mark_candidates=include_mark_candidates,
        )
        write_optimization_plan(plan, plan_output_path, overwrite=overwrite_output)
        result["generated_plan_path"] = str(plan_output_path)
        result["proposed_change_count"] = plan["proposed_change_count"]

    if plan_input_path:
        plan = read_optimization_plan(plan_input_path)
        validate_optimization_plan(plan, geometry=geometry)
        result["loaded_plan_path"] = str(plan_input_path)
        result["proposed_change_count"] = plan["proposed_change_count"]

    should_apply = apply_plan or dry_run_plan
    if should_apply:
        if not plan:
            raise ValueError("--apply-plan or --dry-run-plan requires --plan-input or --plan-output.")
        apply_result = apply_optimization_plan(
            geometry,
            plan,
            dry_run=bool(dry_run_plan or not apply_plan),
        )
        result["applied_change_count"] = apply_result["applied_change_count"]
        result["skipped_change_count"] = apply_result["skipped_change_count"]
        result["destructive_change_count"] = apply_result["destructive_change_count"]
        result["ledger"] = apply_result["ledger"]
        result["geometry_unchanged"] = geometry == apply_result["modified_geometry"]
    return result


def _read_paintstudio_geometry(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Paint Studio geometry JSON: {path}") from exc
    if not looks_like_paint_studio_geometry(data):
        raise ValueError("--output-geometry requires Paint Studio geometry input.")
    return data


def _image_width(path):
    return _image_size(path)[0]


def _image_height(path):
    return _image_size(path)[1]


def _image_size(path):
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def main():
    parser = argparse.ArgumentParser(
        description="FLO analyzes generated Forza livery files against an original image target."
    )
    parser.add_argument("--image", required=True, help="Path to the original reference image.")
    parser.add_argument("--input", required=True, help="Path to the generated .jsdn livery file.")
    parser.add_argument(
        "--input-format",
        choices=("auto", "jsdn", "paintstudio"),
        default="auto",
        help="Input parser to use. Default: auto.",
    )
    parser.add_argument("--report", required=True, help="Path to the JSON report output.")
    parser.add_argument("--preview", help="Optional path to write a rendered PNG preview.")
    parser.add_argument("--diff", help="Optional path to write a PNG visual diff.")
    parser.add_argument("--output-geometry", help="Optional path to write optimized Paint Studio geometry.")
    parser.add_argument(
        "--optimization-mode",
        choices=("noop",),
        default="noop",
        help="Optimization mode for --output-geometry. Default: noop.",
    )
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="Allow replacing an existing --output-geometry file.",
    )
    parser.add_argument("--after-preview", help="Optional preview path for optimized geometry.")
    parser.add_argument("--after-diff", help="Optional diff path for optimized geometry preview.")
    parser.add_argument("--plan-output", help="Optional path to write an optimization plan JSON.")
    parser.add_argument("--plan-input", help="Optional path to read an optimization plan JSON.")
    parser.add_argument(
        "--apply-plan",
        action="store_true",
        help="Apply safe noop/mark_candidate plan actions. Destructive actions are not allowed in v0.6.1.",
    )
    parser.add_argument(
        "--dry-run-plan",
        action="store_true",
        help="Apply plan as a dry run and write ledger data into the report.",
    )
    parser.add_argument(
        "--include-mark-candidates",
        action="store_true",
        help="Include example non-destructive mark_candidate entries in generated noop plans.",
    )
    parser.add_argument(
        "--preview-renderer",
        choices=("default", "paintstudio-source"),
        default="default",
        help="Renderer to use for previews. Default: default.",
    )
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
    output_geometry_path = Path(args.output_geometry) if args.output_geometry else None
    after_preview_path = Path(args.after_preview) if args.after_preview else None
    after_diff_path = Path(args.after_diff) if args.after_diff else None
    plan_output_path = Path(args.plan_output) if args.plan_output else None
    plan_input_path = Path(args.plan_input) if args.plan_input else None

    try:
        report = build_report(
            image_path,
            input_path,
            preview_path,
            diff_path,
            args.input_format,
            args.preview_renderer,
        )
        if output_geometry_path:
            optimization_report = run_geometry_output_pipeline(
                input_path,
                image_path,
                output_geometry_path,
                args.optimization_mode,
                overwrite_output=args.overwrite_output,
                after_preview_path=after_preview_path,
                after_diff_path=after_diff_path,
                preview_renderer=args.preview_renderer,
            )
            report["optimized_geometry"] = optimization_report
        if plan_output_path or plan_input_path or args.apply_plan or args.dry_run_plan:
            plan_report = run_plan_pipeline(
                input_path,
                output_geometry_path=output_geometry_path,
                plan_output_path=plan_output_path,
                plan_input_path=plan_input_path,
                apply_plan=args.apply_plan,
                dry_run_plan=args.dry_run_plan,
                include_mark_candidates=args.include_mark_candidates,
                overwrite_output=args.overwrite_output,
            )
            report["optimization_plan"] = plan_report
    except (
        JsdnParseError,
        PaintStudioGeometryParseError,
        PreviewRenderError,
        PaintStudioSourceRenderError,
        OptimizedGeometryWriteError,
        OptimizationPlanError,
        VisualDiffError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_report(report, report_path)
    print(f"Report written to {report_path}")
    if preview_path:
        print(f"Preview written to {preview_path}")
    if diff_path:
        print(f"Diff written to {diff_path}")
    if output_geometry_path:
        print(f"Optimized geometry written to {output_geometry_path}")
    if after_preview_path:
        print(f"Optimized preview written to {after_preview_path}")
    if after_diff_path:
        print(f"Optimized diff written to {after_diff_path}")
    if plan_output_path:
        print(f"Optimization plan written to {plan_output_path}")
    if plan_input_path and (args.apply_plan or args.dry_run_plan):
        print(f"Optimization plan applied from {plan_input_path}")
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
