import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.removal_impact_scorer import score_removal_impact
from engine.output.removal_impact_writer import write_removal_impact_report


def main():
    parser = argparse.ArgumentParser(description="Score visual impact from accepted-candidate removal simulation.")
    parser.add_argument("--case", help="Case folder, for example cases/case_0001.")
    parser.add_argument("--removal-report", help="removal_simulation_report.json path.")
    parser.add_argument("--before", help="before_preview.png path.")
    parser.add_argument("--after", help="after_preview.png path.")
    parser.add_argument("--output", help="removal_impact_report.json output path.")
    parser.add_argument("--summary", help="removal_impact_summary.txt output path.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--local-padding", type=int, default=8)
    parser.add_argument("--safe-threshold", type=float)
    parser.add_argument("--probably-safe-threshold", type=float)
    parser.add_argument("--risky-threshold", type=float)
    args = parser.parse_args()

    try:
        report = run_scoring(args)
    except Exception as exc:
        print(f"Removal impact scoring failed: {exc}", file=sys.stderr)
        return 1

    print(f"Removal impact status: {report['status']}")
    print(f"Overall decision: {report['overall_decision']}")
    print(f"Report written to {args.output or _paths(args)['output']}")
    return 0


def run_scoring(args):
    paths = _paths(args)
    removal_report = _load_json(paths["removal_report"]) if paths["removal_report"].exists() else None
    report = score_removal_impact(
        str(paths["before"]),
        str(paths["after"]),
        removal_report=removal_report,
        options={
            "local_padding": args.local_padding,
            "safe_threshold": args.safe_threshold,
            "probably_safe_threshold": args.probably_safe_threshold,
            "risky_threshold": args.risky_threshold,
        },
    )
    report["input_paths"]["removal_simulation_report"] = str(paths["removal_report"])
    write_removal_impact_report(report, paths["output"], overwrite=args.overwrite)
    _write_summary(report, paths["summary"])
    return report


def _paths(args):
    case_dir = Path(args.case) if args.case else None
    if not case_dir and not (args.removal_report and args.before and args.after and args.output):
        raise ValueError("Provide --case, or provide --removal-report, --before, --after, and --output.")
    output_dir = case_dir / "removal_simulation" if case_dir else Path(args.output).parent
    return {
        "removal_report": Path(args.removal_report)
        if args.removal_report
        else output_dir / "removal_simulation_report.json",
        "before": Path(args.before) if args.before else output_dir / "before_preview.png",
        "after": Path(args.after) if args.after else output_dir / "after_preview.png",
        "output": Path(args.output) if args.output else output_dir / "removal_impact_report.json",
        "summary": Path(args.summary) if args.summary else output_dir / "removal_impact_summary.txt",
    }


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def _write_summary(report, path):
    lines = [
        "FLO Removal Impact Summary",
        "",
        f"Status: {report['status']}",
        f"Overall decision: {report['overall_decision']}",
        f"Shape counts: {report['shape_counts']}",
        f"Global metrics: {report['global_metrics']}",
        f"Local metrics: {report['local_metrics']}",
        "",
        "Reminder:",
        "- This is only sandbox impact scoring.",
        "- It does not approve final cleanup.",
    ]
    if report.get("warnings"):
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    if report.get("recommendations"):
        lines.extend(["", "Recommendations:"])
        lines.extend(f"- {item}" for item in report["recommendations"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
