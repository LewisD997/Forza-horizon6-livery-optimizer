import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.sandbox_removal_simulator import simulate_accepted_candidate_removal
from engine.output.removal_simulation_writer import (
    write_removal_simulation_report,
    write_sandbox_geometry,
)
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview
from engine.vision.visual_diff import compare_images


def main():
    parser = argparse.ArgumentParser(description="Simulate removing accepted cleanup candidates in a sandbox copy.")
    parser.add_argument("--case", help="Case folder, for example cases/case_0001.")
    parser.add_argument("--geometry", help="Paint Studio geometry JSON path.")
    parser.add_argument("--plan", help="optimization_plan.json path.")
    parser.add_argument("--feedback", help="candidate_feedback.json path.")
    parser.add_argument("--output-dir", help="Removal simulation output folder.")
    parser.add_argument("--base-image", help="Optional source image for canvas size.")
    parser.add_argument("--preview-renderer", default="paintstudio-source", choices=("paintstudio-source",))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-removals", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-sandbox-geometry", action="store_true")
    args = parser.parse_args()

    try:
        report = run_simulation(args)
    except Exception as exc:
        print(f"Removal simulation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Removal simulation status: {report['status']}")
    print(f"Accepted candidates: {report['accepted_candidate_count']}")
    print(f"Simulated removed shapes: {report['simulated_removed_count']}")
    print(f"Report written to {report['outputs']['report']}")
    return 0


def run_simulation(args):
    paths = _resolve_paths(args)
    geometry = _load_json(paths["geometry"])
    plan = _load_json(paths["plan"])
    feedback = _load_json(paths["feedback"])
    report = simulate_accepted_candidate_removal(
        geometry,
        plan,
        feedback,
        options={"max_removals": args.max_removals},
    )
    report.update(
        {
            "input_geometry_path": str(paths["geometry"]),
            "plan_path": str(paths["plan"]),
            "feedback_path": str(paths["feedback"]),
            "output_dir": str(paths["output_dir"]),
            "outputs": {
                "sandbox_geometry": None,
                "before_preview": None,
                "after_preview": None,
                "diff": None,
                "summary": str(paths["summary"]),
                "report": str(paths["report"]),
            },
            "safety": {
                "original_geometry_modified": not report["geometry_unchanged_original"],
                "only_accepted_candidates_considered": True,
                "protected_candidates_blocked": True,
                "rejected_candidates_blocked": True,
                "unsure_candidates_blocked": True,
            },
        }
    )

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    should_write_geometry = args.write_sandbox_geometry or (args.case and not args.dry_run)
    if should_write_geometry:
        report["outputs"]["sandbox_geometry"] = write_sandbox_geometry(
            report["sandbox_geometry"],
            paths["sandbox_geometry"],
            overwrite=args.overwrite,
        )

    _try_render_outputs(report, paths, args)
    if report["status"] == "completed" and report.get("warnings"):
        report["status"] = "completed_with_warnings"
    _write_summary(report, paths["summary"])
    write_removal_simulation_report(report, paths["report"], overwrite=args.overwrite)
    return _strip_sandbox(report)


def _try_render_outputs(report, paths, args):
    try:
        width, height = _image_size(paths["base_image"]) if paths["base_image"] else (None, None)
        metadata = render_paint_studio_preview(
            str(paths["geometry"]),
            str(paths["before_preview"]),
            width=width,
            height=height,
            ssaa=2,
            export_mode="full_canvas_opaque",
        )
        report["outputs"]["before_preview"] = str(paths["before_preview"])
        report.setdefault("render_metadata", {})["before"] = metadata
    except Exception as exc:
        report["warnings"].append(f"Before preview render failed: {exc}")

    if report["status"] == "no_accepted_candidates":
        report["warnings"].append("No accepted candidates available; after preview and diff not generated.")
        return
    if not report["outputs"].get("sandbox_geometry"):
        report["warnings"].append("Sandbox geometry was not written; after preview and diff not generated.")
        return

    try:
        width, height = _image_size(paths["base_image"]) if paths["base_image"] else (None, None)
        metadata = render_paint_studio_preview(
            str(paths["sandbox_geometry"]),
            str(paths["after_preview"]),
            width=width,
            height=height,
            ssaa=2,
            export_mode="full_canvas_opaque",
        )
        report["outputs"]["after_preview"] = str(paths["after_preview"])
        report.setdefault("render_metadata", {})["after"] = metadata
        compare_images(paths["before_preview"], paths["after_preview"], paths["diff"])
        report["outputs"]["diff"] = str(paths["diff"])
    except Exception as exc:
        report["warnings"].append(f"After preview or diff generation failed: {exc}")


def _resolve_paths(args):
    case_dir = Path(args.case) if args.case else None
    if not case_dir and not (args.geometry and args.plan and args.feedback and args.output_dir):
        raise ValueError("Provide --case or provide --geometry, --plan, --feedback, and --output-dir.")
    output_dir = Path(args.output_dir) if args.output_dir else case_dir / "removal_simulation"
    base_image = Path(args.base_image) if args.base_image else (case_dir / "source_full.png" if case_dir else None)
    return {
        "case": case_dir,
        "geometry": Path(args.geometry) if args.geometry else case_dir / "paintstudio_geometry.json",
        "plan": Path(args.plan) if args.plan else case_dir / "optimization_plan.json",
        "feedback": Path(args.feedback) if args.feedback else case_dir / "candidate_review" / "candidate_feedback.json",
        "output_dir": output_dir,
        "base_image": base_image if base_image and base_image.exists() else None,
        "report": output_dir / "removal_simulation_report.json",
        "sandbox_geometry": output_dir / "sandbox_removed_geometry.json",
        "before_preview": output_dir / "before_preview.png",
        "after_preview": output_dir / "after_preview.png",
        "diff": output_dir / "diff.png",
        "summary": output_dir / "removal_simulation_summary.txt",
    }


def _load_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def _write_summary(report, path):
    lines = [
        "FLO Accepted Candidate Removal Simulation",
        "",
        f"Status: {report['status']}",
        f"Input shapes: {report['input_shape_count']}",
        f"Accepted candidates: {report['accepted_candidate_count']}",
        f"Simulated removed shapes: {report['simulated_removed_count']}",
        f"Output shapes: {report['output_shape_count']}",
        f"Original geometry modified: {report['safety']['original_geometry_modified']}",
        "",
        "Safety:",
        "- Only accepted candidates are considered.",
        "- Protected, rejected, and unsure candidates are blocked.",
        "- This script does not modify the original geometry.",
        "- No position, scale, rotation, color, or alpha changes are made.",
    ]
    if report.get("warnings"):
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _image_size(path):
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _strip_sandbox(report):
    result = dict(report)
    result.pop("sandbox_geometry", None)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
