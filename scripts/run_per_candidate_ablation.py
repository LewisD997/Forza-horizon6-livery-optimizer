import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.per_candidate_ablation import run_per_candidate_ablation
from engine.optimizer.trial_feedback_generator import generate_trial_feedback


def main():
    parser = argparse.ArgumentParser(description="Run per-candidate trial ablation.")
    parser.add_argument("--case")
    parser.add_argument("--geometry")
    parser.add_argument("--plan")
    parser.add_argument("--feedback")
    parser.add_argument("--trial-report")
    parser.add_argument("--output-dir")
    parser.add_argument("--change-ids")
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--candidate-type")
    parser.add_argument("--risk-level")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--preview-renderer", default="paintstudio-source", choices=("paintstudio-source",))
    parser.add_argument("--local-padding", type=int, default=8)
    parser.add_argument("--safe-threshold", type=float)
    parser.add_argument("--probably-safe-threshold", type=float)
    parser.add_argument("--risky-threshold", type=float)
    args = parser.parse_args()

    try:
        report = run_from_args(args)
    except Exception as exc:
        print(f"Per-candidate ablation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Per-candidate ablation status: {report['status']}")
    print(f"Tested candidates: {len(report['results'])}")
    print(f"Safe: {len(report['summary']['safe_to_remove'])}")
    print(f"Probably safe: {len(report['summary']['probably_safe'])}")
    print(f"Risky: {len(report['summary']['risky'])}")
    return 0


def run_from_args(args):
    paths = _paths(args)
    geometry = _load_json(paths["geometry"])
    plan = _load_json(paths["plan"])
    feedback = _load_json(paths["feedback"])
    trial_report = _load_json(paths["trial_report"]) if paths["trial_report"] and paths["trial_report"].exists() else None
    candidates = _select_candidates(args, plan, feedback, trial_report)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    report = run_per_candidate_ablation(
        geometry,
        plan,
        feedback,
        candidates,
        options={
            "geometry_path": paths["geometry"],
            "plan_path": paths["plan"],
            "feedback_path": paths["feedback"],
            "trial_report_path": paths["trial_report"],
            "trial_report": trial_report,
            "source_image_path": paths["source"],
            "output_dir": paths["output_dir"],
            "overwrite": args.overwrite,
            "preview_renderer": args.preview_renderer,
            "local_padding": args.local_padding,
            "safe_threshold": args.safe_threshold,
            "probably_safe_threshold": args.probably_safe_threshold,
            "risky_threshold": args.risky_threshold,
        },
    )
    report_path = paths["output_dir"] / "per_candidate_ablation_report.json"
    if report_path.exists() and not args.overwrite:
        raise FileExistsError(f"Ablation report already exists: {report_path}")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_summary(report, paths["output_dir"] / "per_candidate_ablation_summary.txt")
    return report


def _select_candidates(args, plan, feedback, trial_report):
    if args.change_ids:
        return _candidates_from_change_ids(plan, args.change_ids)
    if trial_report is not None:
        return trial_report.get("selected_trial_candidates", [])[: max(0, args.max_candidates)]
    result = generate_trial_feedback(
        plan,
        feedback,
        options={
            "max_trial_accepts": args.max_candidates,
            "candidate_type": args.candidate_type,
            "risk_level": args.risk_level,
        },
    )
    return result.get("selected_trial_candidates", [])


def _candidates_from_change_ids(plan, change_ids):
    plan_by_id = {change.get("change_id"): change for change in plan.get("changes", []) if change.get("change_id")}
    candidates = []
    for change_id in [part.strip() for part in change_ids.split(",") if part.strip()]:
        change = plan_by_id.get(change_id)
        metadata = (change or {}).get("metadata") or {}
        candidates.append(
            {
                "change_id": change_id,
                "shape_index": (change or {}).get("shape_index"),
                "shape_uid": (change or {}).get("shape_uid"),
                "candidate_type": metadata.get("candidate_type"),
                "risk_level": (change or {}).get("risk_level"),
                "trial_score": None,
            }
        )
    return candidates


def _paths(args):
    case_dir = Path(args.case) if args.case else None
    if not case_dir and not (args.geometry and args.plan and args.feedback and args.output_dir):
        raise ValueError("Provide --case or explicit --geometry, --plan, --feedback, and --output-dir.")
    trial_report = Path(args.trial_report) if args.trial_report else None
    if case_dir and not trial_report:
        default_trial_report = case_dir / "removal_simulation" / "trial" / "trial_workflow_report.json"
        trial_report = default_trial_report if default_trial_report.exists() else None
    source = case_dir / "source_full.png" if case_dir and (case_dir / "source_full.png").exists() else None
    return {
        "case": case_dir,
        "geometry": Path(args.geometry) if args.geometry else case_dir / "paintstudio_geometry.json",
        "plan": Path(args.plan) if args.plan else case_dir / "optimization_plan.json",
        "feedback": Path(args.feedback) if args.feedback else case_dir / "candidate_review" / "candidate_feedback.json",
        "trial_report": trial_report,
        "source": source,
        "output_dir": Path(args.output_dir) if args.output_dir else case_dir / "removal_simulation" / "ablation",
    }


def _load_json(path):
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"Required JSON input missing: {path}")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def _write_summary(report, path):
    lines = [
        "FLO Per-Candidate Trial Ablation",
        "",
        f"Status: {report['status']}",
        f"Total tested candidates: {len(report['results'])}",
        f"safe_to_remove: {len(report['summary']['safe_to_remove'])}",
        f"probably_safe: {len(report['summary']['probably_safe'])}",
        f"risky: {len(report['summary']['risky'])}",
        f"failed: {len(report['summary']['failed'])}",
        f"not_applicable: {len(report['summary']['not_applicable'])}",
        "",
        "Candidates:",
    ]
    for result in report["results"]:
        impact = result["impact"]
        lines.append(
            "- {change_id}: shape={shape_index}, type={candidate_type}, risk={risk_level}, "
            "decision={decision}, changed={changed}, mean={mean}, local={local}".format(
                change_id=result.get("change_id"),
                shape_index=result.get("shape_index"),
                candidate_type=result.get("candidate_type"),
                risk_level=result.get("risk_level"),
                decision=impact.get("overall_decision"),
                changed=impact.get("changed_pixel_ratio"),
                mean=impact.get("mean_abs_diff"),
                local=impact.get("local_changed_pixel_ratio"),
            )
        )
    batch = report.get("batch_reference") or {}
    lines.extend(
        [
            "",
            "Batch reference:",
            f"Batch decision: {batch.get('batch_decision')}",
            f"Batch changed pixel ratio: {batch.get('batch_changed_pixel_ratio')}",
            f"Batch candidate count: {batch.get('batch_candidate_count')}",
            "",
            f"Individual risky candidates: {report['summary']['risky']}",
            f"Individual safer candidates: {report['summary']['safe_to_remove'] + report['summary']['probably_safe']}",
            "",
            "Reminder:",
            "This is sandbox-only.",
            "No official cleanup geometry is written.",
            "safe_to_remove is not final cleanup approval.",
        ]
    )
    if report.get("warnings"):
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
