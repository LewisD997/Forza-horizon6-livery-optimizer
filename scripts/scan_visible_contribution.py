import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.visible_contribution_scanner import scan_visible_contribution


def main():
    parser = argparse.ArgumentParser(description="Scan visible contribution of sandbox-removed shapes.")
    parser.add_argument("--case")
    parser.add_argument("--geometry")
    parser.add_argument("--plan")
    parser.add_argument("--feedback")
    parser.add_argument("--output-dir")
    parser.add_argument(
        "--scope",
        default="low_risk_candidate",
        choices=("candidate_plan", "low_risk_candidate", "feedback_filtered", "explicit", "layer_range"),
    )
    parser.add_argument("--change-ids")
    parser.add_argument("--shape-indexes")
    parser.add_argument("--start-index", type=int)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-scan-shapes", type=int, default=30)
    parser.add_argument("--exclude-protected", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--exclude-rejected", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-unsure", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-accepted", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--crop-padding", type=int, default=32)
    parser.add_argument("--upscale", type=int, default=4)
    parser.add_argument("--amplify-diff", type=float, default=6.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--preview-renderer", default="paintstudio-source", choices=("paintstudio-source",))
    parser.add_argument("--local-padding", type=int, default=8)
    parser.add_argument("--zero-threshold", type=float)
    parser.add_argument("--barely-threshold", type=float)
    parser.add_argument("--minor-threshold", type=float)
    parser.add_argument("--important-threshold", type=float)
    args = parser.parse_args()

    try:
        report = run_from_args(args)
    except Exception as exc:
        print(f"Visible contribution scan failed: {exc}", file=sys.stderr)
        return 1

    print(f"Visible contribution scan status: {report['status']}")
    print(f"Scanned shapes: {report['scanned_shape_count']}")
    print(f"Safe delete pool: {len(report['summary']['safe_delete_pool'])}")
    print(f"Replacement candidates: {len(report['summary']['replacement_candidate'])}")
    print(f"Protected: {len(report['summary']['protect_candidate'])}")
    return 0


def run_from_args(args):
    paths = _paths(args)
    geometry = _load_json(paths["geometry"])
    plan = _load_json(paths["plan"]) if paths["plan"] and paths["plan"].exists() else {}
    feedback = _load_json(paths["feedback"]) if paths["feedback"] and paths["feedback"].exists() else {}
    return scan_visible_contribution(
        geometry,
        plan=plan,
        feedback=feedback,
        options={
            "scope": args.scope,
            "geometry_path": paths["geometry"],
            "plan_path": paths["plan"],
            "feedback_path": paths["feedback"],
            "source_image_path": paths["source"],
            "output_dir": paths["output_dir"],
            "change_ids": args.change_ids,
            "shape_indexes": args.shape_indexes,
            "start_index": args.start_index,
            "end_index": args.end_index,
            "max_scan_shapes": args.max_scan_shapes,
            "exclude_protected": args.exclude_protected,
            "exclude_rejected": args.exclude_rejected,
            "include_unsure": args.include_unsure,
            "include_accepted": args.include_accepted,
            "crop_padding": args.crop_padding,
            "upscale": args.upscale,
            "amplify_diff": args.amplify_diff,
            "overwrite": args.overwrite,
            "preview_renderer": args.preview_renderer,
            "local_padding": args.local_padding,
            "zero_threshold": args.zero_threshold,
            "barely_threshold": args.barely_threshold,
            "minor_threshold": args.minor_threshold,
            "important_threshold": args.important_threshold,
        },
    )


def _paths(args):
    case_dir = Path(args.case) if args.case else None
    if not case_dir and not (args.geometry and args.output_dir):
        raise ValueError("Provide --case or explicit --geometry and --output-dir.")
    source = case_dir / "source_full.png" if case_dir and (case_dir / "source_full.png").exists() else None
    return {
        "case": case_dir,
        "geometry": Path(args.geometry) if args.geometry else case_dir / "paintstudio_geometry.json",
        "plan": Path(args.plan) if args.plan else (case_dir / "optimization_plan.json" if case_dir else None),
        "feedback": Path(args.feedback) if args.feedback else (case_dir / "candidate_review" / "candidate_feedback.json" if case_dir else None),
        "source": source,
        "output_dir": Path(args.output_dir) if args.output_dir else case_dir / "visible_contribution",
    }


def _load_json(path):
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"Required JSON input missing: {path}")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
