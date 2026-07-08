import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.removal_impact_scorer import score_removal_impact
from engine.optimizer.sandbox_removal_simulator import simulate_accepted_candidate_removal
from engine.optimizer.trial_feedback_generator import TRIAL_VERSION, generate_trial_feedback
from engine.output.removal_impact_writer import write_removal_impact_report
from engine.output.removal_simulation_writer import write_removal_simulation_report, write_sandbox_geometry
from engine.output.trial_feedback_writer import validate_trial_feedback, write_trial_feedback
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview
from engine.vision.visual_diff import compare_images


def main():
    parser = argparse.ArgumentParser(description="Run a safe trial accepted-candidate workflow.")
    parser.add_argument("--case", help="Case folder, for example cases/case_0001.")
    parser.add_argument("--geometry")
    parser.add_argument("--plan")
    parser.add_argument("--feedback")
    parser.add_argument("--output-dir")
    parser.add_argument("--max-trial-accepts", type=int, default=5)
    parser.add_argument("--candidate-type")
    parser.add_argument("--risk-level")
    parser.add_argument("--change-ids")
    parser.add_argument("--allow-review-only", action="store_true")
    parser.add_argument("--allow-early-shapes", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--preview-renderer", default="paintstudio-source", choices=("paintstudio-source",))
    parser.add_argument("--local-padding", type=int, default=8)
    args = parser.parse_args()

    try:
        report = run_workflow(args)
    except Exception as exc:
        print(f"Trial workflow failed: {exc}", file=sys.stderr)
        return 1

    print(f"Trial workflow status: {report['status']}")
    print(f"Selected trial candidates: {len(report['selected_trial_candidates'])}")
    print(f"Simulated removed: {report['removal_summary']['simulated_removed_count']}")
    print(f"Impact decision: {report['impact_summary']['overall_decision']}")
    return 0


def run_workflow(args):
    paths = _paths(args)
    geometry = _load_json(paths["geometry"])
    original_geometry = copy.deepcopy(geometry)
    plan = _load_json(paths["plan"])
    feedback = _load_json(paths["feedback"])
    original_feedback = copy.deepcopy(feedback)
    warnings = []

    trial_result = generate_trial_feedback(
        plan,
        feedback,
        options={
            "max_trial_accepts": args.max_trial_accepts,
            "candidate_type": args.candidate_type,
            "risk_level": args.risk_level,
            "change_ids": args.change_ids,
            "allow_review_only": args.allow_review_only,
            "allow_early_shapes": args.allow_early_shapes,
        },
    )
    warnings.extend(trial_result.get("warnings", []))
    validate_trial_feedback(trial_result["trial_feedback"], original_feedback, plan)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    trial_paths = write_trial_feedback(
        trial_result,
        paths["trial_feedback"],
        paths["trial_feedback_report"],
        overwrite=args.overwrite,
    )

    removal = simulate_accepted_candidate_removal(geometry, plan, trial_result["trial_feedback"])
    removal.update(
        {
            "input_geometry_path": str(paths["geometry"]),
            "plan_path": str(paths["plan"]),
            "feedback_path": str(paths["trial_feedback"]),
            "output_dir": str(paths["output_dir"]),
            "outputs": {
                "sandbox_geometry": None,
                "before_preview": None,
                "after_preview": None,
                "diff": None,
                "summary": None,
                "report": str(paths["removal_report"]),
            },
            "safety": {
                "original_geometry_modified": not removal["geometry_unchanged_original"],
                "only_accepted_candidates_considered": True,
                "protected_candidates_blocked": True,
                "rejected_candidates_blocked": True,
                "unsure_candidates_blocked": True,
            },
        }
    )

    if removal["simulated_removed_count"] > 0:
        removal["outputs"]["sandbox_geometry"] = write_sandbox_geometry(
            removal["sandbox_geometry"], paths["sandbox_geometry"], overwrite=args.overwrite
        )
        _render_trial_previews(removal, paths)
    else:
        removal["warnings"].append("No trial candidates were removed; previews after removal were not generated.")

    if removal["status"] == "completed" and removal.get("warnings"):
        removal["status"] = "completed_with_warnings"
    write_removal_simulation_report(removal, paths["removal_report"], overwrite=args.overwrite)

    impact = score_removal_impact(
        removal["outputs"].get("before_preview"),
        removal["outputs"].get("after_preview"),
        removal_report=removal,
        plan=plan,
        feedback=trial_result["trial_feedback"],
        options={"local_padding": args.local_padding},
    )
    impact["input_paths"]["removal_simulation_report"] = str(paths["removal_report"])
    write_removal_impact_report(impact, paths["impact_report"], overwrite=args.overwrite)

    workflow = _workflow_report(
        paths,
        trial_paths,
        feedback,
        trial_result,
        removal,
        impact,
        original_geometry == geometry,
        original_feedback == feedback,
        warnings,
    )
    paths["workflow_report"].write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_summary(workflow, paths["summary"])
    return workflow


def _render_trial_previews(removal, paths):
    width, height = _image_size(paths["source"]) if paths["source"] else (None, None)
    before = render_paint_studio_preview(
        str(paths["geometry"]),
        str(paths["before_preview"]),
        width=width,
        height=height,
        ssaa=2,
        export_mode="full_canvas_opaque",
    )
    after = render_paint_studio_preview(
        str(paths["sandbox_geometry"]),
        str(paths["after_preview"]),
        width=width,
        height=height,
        ssaa=2,
        export_mode="full_canvas_opaque",
    )
    compare_images(paths["before_preview"], paths["after_preview"], paths["diff"])
    removal["outputs"]["before_preview"] = str(paths["before_preview"])
    removal["outputs"]["after_preview"] = str(paths["after_preview"])
    removal["outputs"]["diff"] = str(paths["diff"])
    removal["render_metadata"] = {"before": before, "after": after}


def _workflow_report(paths, trial_paths, original_feedback, trial_result, removal, impact, geometry_same, feedback_same, warnings):
    status = "completed"
    if not trial_result.get("selected_trial_candidates"):
        status = "no_eligible_trial_candidates"
    elif warnings or removal.get("warnings") or impact.get("warnings"):
        status = "completed_with_warnings"
    return {
        "trial_version": TRIAL_VERSION,
        "status": status,
        "input_paths": {
            "geometry": str(paths["geometry"]),
            "plan": str(paths["plan"]),
            "original_feedback": str(paths["feedback"]),
        },
        "output_paths": {
            "trial_feedback": trial_paths["trial_feedback"],
            "trial_feedback_report": trial_paths["trial_feedback_report"],
            "sandbox_geometry": removal["outputs"].get("sandbox_geometry"),
            "before_preview": removal["outputs"].get("before_preview"),
            "after_preview": removal["outputs"].get("after_preview"),
            "diff": removal["outputs"].get("diff"),
            "removal_simulation_report": str(paths["removal_report"]),
            "removal_impact_report": str(paths["impact_report"]),
            "summary": str(paths["summary"]),
        },
        "original_feedback_counts": original_feedback.get("counts_by_status", {}),
        "trial_feedback_counts": trial_result["trial_feedback"].get("counts_by_status", {}),
        "selected_trial_candidates": trial_result.get("selected_trial_candidates", []),
        "skipped_candidates": trial_result.get("skipped_candidates", []),
        "removal_summary": {
            "accepted_candidate_count": removal.get("accepted_candidate_count", 0),
            "simulated_removed_count": removal.get("simulated_removed_count", 0),
            "input_shape_count": removal.get("input_shape_count", 0),
            "output_shape_count": removal.get("output_shape_count", 0),
        },
        "impact_summary": {
            "status": impact.get("status"),
            "overall_decision": impact.get("overall_decision"),
            "global_changed_pixel_ratio": (impact.get("global_metrics") or {}).get("changed_pixel_ratio"),
            "mean_abs_diff": (impact.get("global_metrics") or {}).get("mean_abs_diff"),
        },
        "safety": {
            "original_geometry_modified": not geometry_same,
            "original_feedback_modified": not feedback_same,
            "trial_feedback_only": True,
            "official_cleanup_output_written": False,
        },
        "warnings": warnings + removal.get("warnings", []) + impact.get("warnings", []),
    }


def _paths(args):
    case_dir = Path(args.case) if args.case else None
    if not case_dir and not (args.geometry and args.plan and args.feedback and args.output_dir):
        raise ValueError("Provide --case or explicit --geometry, --plan, --feedback, and --output-dir.")
    output_dir = Path(args.output_dir) if args.output_dir else case_dir / "removal_simulation" / "trial"
    source = case_dir / "source_full.png" if case_dir and (case_dir / "source_full.png").exists() else None
    return {
        "case": case_dir,
        "geometry": Path(args.geometry) if args.geometry else case_dir / "paintstudio_geometry.json",
        "plan": Path(args.plan) if args.plan else case_dir / "optimization_plan.json",
        "feedback": Path(args.feedback) if args.feedback else case_dir / "candidate_review" / "candidate_feedback.json",
        "source": source,
        "output_dir": output_dir,
        "trial_feedback": output_dir / "candidate_feedback_trial.json",
        "trial_feedback_report": output_dir / "trial_feedback_report.json",
        "sandbox_geometry": output_dir / "sandbox_removed_geometry_trial.json",
        "before_preview": output_dir / "before_preview.png",
        "after_preview": output_dir / "after_preview.png",
        "diff": output_dir / "diff.png",
        "removal_report": output_dir / "removal_simulation_report_trial.json",
        "impact_report": output_dir / "removal_impact_report_trial.json",
        "workflow_report": output_dir / "trial_workflow_report.json",
        "summary": output_dir / "trial_workflow_summary.txt",
    }


def _load_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Required input missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def _write_summary(report, path):
    lines = [
        "FLO Trial Accepted Candidate Workflow",
        "",
        f"Status: {report['status']}",
        f"Selected candidates: {len(report['selected_trial_candidates'])}",
        f"Selected change IDs: {[item['change_id'] for item in report['selected_trial_candidates']]}",
        f"Original feedback counts: {report['original_feedback_counts']}",
        f"Trial feedback counts: {report['trial_feedback_counts']}",
        f"Removed shapes: {report['removal_summary']['simulated_removed_count']}",
        f"Impact: {report['impact_summary']['status']} / {report['impact_summary']['overall_decision']}",
        "",
        "Safety:",
        f"Original geometry modified: {report['safety']['original_geometry_modified']}",
        f"Original feedback modified: {report['safety']['original_feedback_modified']}",
        f"Official cleanup output written: {report['safety']['official_cleanup_output_written']}",
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


if __name__ == "__main__":
    raise SystemExit(main())
