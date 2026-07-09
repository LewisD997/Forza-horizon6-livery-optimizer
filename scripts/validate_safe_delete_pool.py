import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.safe_delete_pool_validator import validate_safe_delete_pool


def main():
    parser = argparse.ArgumentParser(description="Validate FLO safe_delete_pool candidates in a sandbox batch.")
    parser.add_argument("--case")
    parser.add_argument("--geometry")
    parser.add_argument("--visible-report")
    parser.add_argument("--feedback")
    parser.add_argument("--output-dir")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--preview-renderer", default="paintstudio-source", choices=("paintstudio-source",))
    parser.add_argument("--local-padding", type=int, default=8)
    parser.add_argument("--safe-threshold", type=float)
    parser.add_argument("--probably-safe-threshold", type=float)
    parser.add_argument("--risky-threshold", type=float)
    parser.add_argument("--write-sandbox-geometry", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()

    try:
        report = run_from_args(args)
    except Exception as exc:
        print(f"Safe delete pool validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Safe delete validation status: {report['status']}")
    print(f"Safe delete candidates: {report['safe_delete_candidate_count']}")
    print(f"Simulated removed: {report['simulated_removed_count']}")
    print(f"Output shapes: {report['output_shape_count']}")
    print(f"Impact decision: {report['impact_summary']['overall_decision']}")
    return 0


def run_from_args(args):
    paths = _paths(args)
    geometry = _load_json(paths["geometry"])
    visible_report = _load_json(paths["visible_report"])
    feedback = _load_json(paths["feedback"]) if paths["feedback"] and paths["feedback"].exists() else {}
    return validate_safe_delete_pool(
        geometry,
        visible_report,
        options={
            "geometry_path": paths["geometry"],
            "visible_report_path": paths["visible_report"],
            "feedback_path": paths["feedback"],
            "feedback": feedback,
            "source_image_path": paths["source"],
            "output_dir": paths["output_dir"],
            "overwrite": args.overwrite,
            "preview_renderer": args.preview_renderer,
            "local_padding": args.local_padding,
            "safe_threshold": args.safe_threshold,
            "probably_safe_threshold": args.probably_safe_threshold,
            "risky_threshold": args.risky_threshold,
            "write_sandbox_geometry": args.write_sandbox_geometry,
            "no_render": args.no_render,
        },
    )


def _paths(args):
    case_dir = Path(args.case) if args.case else None
    if not case_dir and not (args.geometry and args.visible_report and args.output_dir):
        raise ValueError("Provide --case or explicit --geometry, --visible-report, and --output-dir.")
    source = case_dir / "source_full.png" if case_dir and (case_dir / "source_full.png").exists() else None
    return {
        "case": case_dir,
        "geometry": Path(args.geometry) if args.geometry else case_dir / "paintstudio_geometry.json",
        "visible_report": Path(args.visible_report)
        if args.visible_report
        else case_dir / "visible_contribution" / "visible_contribution_report.json",
        "feedback": Path(args.feedback)
        if args.feedback
        else (case_dir / "candidate_review" / "candidate_feedback.json" if case_dir else None),
        "source": source,
        "output_dir": Path(args.output_dir) if args.output_dir else case_dir / "safe_delete_validation",
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
