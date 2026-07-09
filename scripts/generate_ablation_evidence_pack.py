import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.visualization.ablation_evidence_pack import generate_ablation_evidence_pack


def main():
    parser = argparse.ArgumentParser(description="Generate ablation evidence pack and auto triage.")
    parser.add_argument("--case")
    parser.add_argument("--ablation-report")
    parser.add_argument("--output-dir")
    parser.add_argument("--crop-padding", type=int, default=32)
    parser.add_argument("--upscale", type=int, default=4)
    parser.add_argument("--amplify-diff", type=float, default=6.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--candidate-id")
    parser.add_argument("--max-candidates", type=int)
    args = parser.parse_args()

    try:
        report = run_from_args(args)
    except Exception as exc:
        print(f"Ablation evidence pack failed: {exc}", file=sys.stderr)
        return 1

    print(f"Evidence pack status: {report['status']}")
    print(f"Candidates: {report['candidate_count']}")
    print(f"Triage counts: {report['triage_counts']}")
    return 0


def run_from_args(args):
    paths = _paths(args)
    ablation_report = _load_json(paths["ablation_report"])
    report = generate_ablation_evidence_pack(
        ablation_report,
        str(paths["output_dir"]),
        options={
            "source_ablation_report": paths["ablation_report"],
            "crop_padding": args.crop_padding,
            "upscale": args.upscale,
            "amplify_diff": args.amplify_diff,
            "overwrite": args.overwrite,
            "candidate_id": args.candidate_id,
            "max_candidates": args.max_candidates,
        },
    )
    return report


def _paths(args):
    case_dir = Path(args.case) if args.case else None
    if not case_dir and not (args.ablation_report and args.output_dir):
        raise ValueError("Provide --case or explicit --ablation-report and --output-dir.")
    ablation_report = (
        Path(args.ablation_report)
        if args.ablation_report
        else case_dir / "removal_simulation" / "ablation" / "per_candidate_ablation_report.json"
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else case_dir / "removal_simulation" / "ablation" / "evidence_pack"
    )
    return {"case": case_dir, "ablation_report": ablation_report, "output_dir": output_dir}


def _load_json(path):
    if not Path(path).exists():
        raise FileNotFoundError(f"Required ablation report missing: {path}")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
