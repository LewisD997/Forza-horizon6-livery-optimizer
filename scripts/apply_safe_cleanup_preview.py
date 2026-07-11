import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.removal_impact_scorer import score_removal_impact
from engine.optimizer.safe_cleanup_preview_applier import apply_safe_cleanup_preview, reconstruct_original_from_preview
from engine.output.safe_cleanup_preview_writer import (
    validate_preview_cleanup_output, write_preview_cleanup_geometry,
    write_safe_cleanup_apply_report, write_safe_cleanup_ledger,
)
from engine.renderer.export_alignment import compare_images as compare_to_reference
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview
from engine.vision.visual_diff import compare_images as write_visual_diff


def main():
    parser = _parser()
    try:
        report = run_from_args(parser.parse_args())
    except Exception as exc:
        print(f"Safe cleanup apply preview failed: {exc}", file=sys.stderr)
        return 1
    print(f"Status: {report['status']}")
    print(f"Applied removals: {report['applied_removal_count']}")
    print(f"Preview geometry: {report['output_paths']['preview_geometry']}")
    return 0


def run_from_args(args):
    paths = _resolve_paths(args)
    geometry = _load(paths["geometry"])
    proposal = _load(paths["proposal"])
    visible = _load_optional(paths["visible_report"])
    feedback = _load_optional(paths["feedback"])
    original_geometry = copy.deepcopy(geometry)
    original_feedback = copy.deepcopy(feedback)
    result = apply_safe_cleanup_preview(
        geometry, proposal, visible, feedback,
        {"max_removals": args.max_removals},
    )
    output_dir = paths["output_dir"]
    outputs = _outputs(output_dir)
    overwrite = bool(args.overwrite)
    write_preview_cleanup_geometry(result["preview_geometry"], outputs["preview_geometry"], overwrite, paths["geometry"])
    write_safe_cleanup_ledger(result["application_ledger"], outputs["ledger"], overwrite)

    reconstructed = reconstruct_original_from_preview(result["preview_geometry"], result["application_ledger"])
    rollback_passed = reconstructed == original_geometry
    write_preview_cleanup_geometry(reconstructed, outputs["rollback_geometry"], overwrite, paths["geometry"])

    impact = _no_render_impact()
    if not args.no_render:
        _render(paths["geometry"], outputs["before_preview"], paths["source_image"])
        _render(outputs["preview_geometry"], outputs["after_preview"], paths["source_image"])
        write_visual_diff(outputs["before_preview"], outputs["after_preview"], outputs["diff"])
        removal_report = {
            "input_shape_count": result["input_shape_count"], "output_shape_count": result["output_shape_count"],
            "simulated_removed_count": result["applied_removal_count"], "removed_shapes": result["applied_removals"],
        }
        impact = score_removal_impact(outputs["before_preview"], outputs["after_preview"], removal_report=removal_report)

    reference = _reference_comparison(paths["source_image"], outputs, args)
    write_safe_cleanup_apply_report(reference, outputs["reference_comparison"], overwrite)
    report = _build_report(result, paths, outputs, impact, reference, rollback_passed, original_geometry, reconstructed)
    validate_preview_cleanup_output(original_geometry, result["preview_geometry"], report)
    _write_summary(report, outputs["summary"], overwrite)
    if not args.no_render:
        _write_evidence_sheet(report, outputs, overwrite)
    write_safe_cleanup_apply_report(report, outputs["report"], overwrite)
    if geometry != original_geometry or feedback != original_feedback:
        raise RuntimeError("Original input objects changed during preview apply.")
    return report


def _parser():
    parser = argparse.ArgumentParser(description="Apply a validated safe-delete proposal to preview-only geometry.")
    parser.add_argument("--case")
    parser.add_argument("--geometry")
    parser.add_argument("--proposal")
    parser.add_argument("--visible-report")
    parser.add_argument("--feedback")
    parser.add_argument("--source-image")
    parser.add_argument("--output-dir")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--preview-renderer", choices=["paintstudio-source"], default="paintstudio-source")
    parser.add_argument("--max-removals", type=int)
    parser.add_argument("--write-rollback-preview", action="store_true")
    parser.add_argument("--skip-reference-comparison", action="store_true")
    return parser


def _resolve_paths(args):
    case = Path(args.case) if args.case else None
    def choose(value, relative): return Path(value) if value else (case / relative if case else None)
    paths = {
        "geometry": choose(args.geometry, "paintstudio_geometry.json"),
        "proposal": choose(args.proposal, "safe_delete_validation/safe_delete_cleanup_proposal.json"),
        "visible_report": choose(args.visible_report, "visible_contribution/visible_contribution_report.json"),
        "feedback": choose(args.feedback, "candidate_review/candidate_feedback.json"),
        "source_image": choose(args.source_image, "source_full.png"),
        "output_dir": Path(args.output_dir) if args.output_dir else (case / "safe_cleanup_apply_preview" if case else Path("output/safe_cleanup_apply_preview")),
    }
    if not paths["geometry"] or not paths["proposal"]: raise ValueError("Provide --case or both --geometry and --proposal.")
    return paths


def _outputs(root):
    return {key: str(root / name) for key, name in {
        "preview_geometry": "preview_safe_cleanup_geometry.json", "report": "safe_cleanup_apply_preview_report.json",
        "ledger": "safe_cleanup_application_ledger.json", "summary": "safe_cleanup_apply_preview_summary.txt",
        "before_preview": "before_preview.png", "after_preview": "after_preview.png", "diff": "before_after_diff.png",
        "evidence_sheet": "evidence_sheet.png", "rollback_geometry": "rollback_preview_geometry.json",
        "reference_comparison": "reference_comparison.json",
    }.items()}


def _render(geometry, output, source):
    width = height = None
    if source and Path(source).exists():
        from PIL import Image
        with Image.open(source) as image: width, height = image.size
    render_paint_studio_preview(str(geometry), str(output), width=width, height=height, ssaa=2, export_mode="full_canvas_opaque")


def _reference_comparison(source, outputs, args):
    if args.skip_reference_comparison: return _reference_unavailable("Skipped by --skip-reference-comparison.")
    if args.no_render: return _reference_unavailable("Rendering disabled.")
    if not source or not Path(source).exists(): return _reference_unavailable("Source image is unavailable.")
    try:
        before = compare_to_reference(outputs["before_preview"], source)
        after = compare_to_reference(outputs["after_preview"], source)
        delta = round(after["difference_score"] - before["difference_score"], 6)
        return {"status": "completed", "metric_name": "mean_normalized_rgb_absolute_difference",
                "alignment_method": after.get("alignment", {}).get("mode"),
                "before_error_to_reference": before["difference_score"], "after_error_to_reference": after["difference_score"],
                "delta_reference_error": delta, "reference_non_worsening": delta <= 0.000001, "warnings": []}
    except Exception as exc: return _reference_unavailable(str(exc))


def _reference_unavailable(reason):
    return {"status": "not_available", "metric_name": None, "alignment_method": None,
            "before_error_to_reference": None, "after_error_to_reference": None,
            "delta_reference_error": None, "reference_non_worsening": None, "warnings": [reason]}


def _build_report(result, paths, outputs, impact, reference, rollback_passed, original, reconstructed):
    global_metrics = impact.get("global_metrics") or {}
    return {
        "apply_preview_version": "0.6.13", "status": result["status"],
        "input_paths": {key: str(value) if value else None for key, value in paths.items() if key != "output_dir"},
        "output_paths": outputs, "input_shape_count": result["input_shape_count"],
        "proposal_candidate_count": result["proposal_candidate_count"], "applied_removal_count": result["applied_removal_count"],
        "skipped_removal_count": result["skipped_removal_count"], "output_shape_count": result["output_shape_count"],
        "applied_change_ids": [item["change_id"] for item in result["applied_removals"]],
        "applied_removals": result["applied_removals"], "skipped_removals": result["skipped_removals"],
        "preview_impact": {"changed_pixel_count": global_metrics.get("changed_pixel_count"),
            "changed_pixel_ratio": global_metrics.get("changed_pixel_ratio"), "mean_abs_diff": global_metrics.get("mean_abs_diff"),
            "max_abs_diff": global_metrics.get("max_abs_diff"), "changed_bbox": global_metrics.get("changed_bbox"),
            "image_size_consistent": impact.get("status") != "failed", "overall_decision": impact.get("overall_decision", "not_applicable")},
        "reference_comparison": reference,
        "rollback_validation": {"passed": rollback_passed, "reconstructed_matches_original": reconstructed == original,
            "original_geometry_hash": _hash(original), "preview_geometry_hash": _hash(result["preview_geometry"]),
            "reconstructed_geometry_hash": _hash(reconstructed)},
        "safety": result["safety"], "warnings": result["warnings"] + reference.get("warnings", []),
    }


def _write_summary(report, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite: raise FileExistsError(output)
    lines = ["FLO Safe Cleanup Apply Preview", "PREVIEW ONLY", "",
             f"Status: {report['status']}", f"Applied removals: {report['applied_change_ids']}",
             f"Skipped removals: {report['skipped_removal_count']}",
             f"Shapes: {report['input_shape_count']} -> {report['output_shape_count']}",
             f"Changed pixel ratio: {report['preview_impact']['changed_pixel_ratio']}",
             f"Reference comparison: {report['reference_comparison']['status']}",
             f"Rollback validation: {report['rollback_validation']['passed']}", "",
             "This output is preview-only.", "No official optimized geometry was written."]
    output.write_text("\n".join(lines), encoding="utf-8")


def _write_evidence_sheet(report, outputs, overwrite):
    from PIL import Image, ImageDraw
    output = Path(outputs["evidence_sheet"])
    if output.exists() and not overwrite: raise FileExistsError(output)
    images = [Image.open(outputs[key]).convert("RGB") for key in ("before_preview", "after_preview", "diff")]
    for image in images: image.thumbnail((320, 240))
    sheet = Image.new("RGB", (1000, 360), "white"); draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), "FLO SAFE CLEANUP APPLY - PREVIEW ONLY", fill="red")
    draw.text((12, 32), f"Removed: {', '.join(report['applied_change_ids']) or 'none'}", fill="black")
    draw.text((12, 50), f"Impact: {report['preview_impact']['overall_decision']}  rollback={report['rollback_validation']['passed']}", fill="black")
    draw.text((12, 68), f"Reference: {report['reference_comparison']['status']}", fill="black")
    for x, label, image in zip((10, 340, 670), ("before", "after", "diff"), images):
        draw.text((x, 96), label, fill="black"); sheet.paste(image, (x, 116))
    sheet.save(output)


def _no_render_impact(): return {"status": "not_applicable", "overall_decision": "not_applicable", "global_metrics": {}}
def _hash(data): return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest().upper()
def _load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def _load_optional(path): return _load(path) if path and Path(path).exists() else None


if __name__ == "__main__":
    raise SystemExit(main())
