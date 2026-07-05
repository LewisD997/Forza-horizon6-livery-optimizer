import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_feedback import create_feedback_template
from engine.output.candidate_feedback_writer import export_feedback_csv, write_candidate_feedback


def main():
    parser = argparse.ArgumentParser(description="Create a candidate feedback template from optimization_plan.json.")
    parser.add_argument("--case", help="Case folder, for example cases/case_0001.")
    parser.add_argument("--plan", help="Optimization plan path.")
    parser.add_argument("--output", help="Feedback JSON output path.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    case_dir = Path(args.case) if args.case else None
    if case_dir is None and (not args.plan or not args.output):
        parser.error("Provide --case, or provide both --plan and --output.")
    plan_path = Path(args.plan) if args.plan else case_dir / "optimization_plan.json"
    output_path = Path(args.output) if args.output else case_dir / "candidate_review" / "candidate_feedback.json"
    csv_path = output_path.with_suffix(".csv")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    feedback = create_feedback_template(plan)
    feedback["source_plan_path"] = str(plan_path)
    write_candidate_feedback(feedback, output_path, overwrite=args.overwrite)
    export_feedback_csv(feedback, csv_path)
    print(f"Candidate feedback written to {output_path}")
    print(f"Candidate feedback CSV written to {csv_path}")
    print(f"Total items: {feedback['total_feedback_items']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
