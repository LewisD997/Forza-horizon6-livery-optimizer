import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_feedback import CandidateFeedbackError, validate_candidate_feedback
from engine.output.candidate_feedback_writer import read_candidate_feedback


def main():
    parser = argparse.ArgumentParser(description="Validate candidate feedback JSON.")
    parser.add_argument("--feedback", required=True)
    parser.add_argument("--plan")
    args = parser.parse_args()

    try:
        feedback = read_candidate_feedback(args.feedback)
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if args.plan else None
        result = validate_candidate_feedback(feedback, plan=plan)
    except (OSError, ValueError, CandidateFeedbackError) as exc:
        print(f"Candidate feedback validation failed: {exc}", file=sys.stderr)
        return 1

    print("Candidate feedback validation passed.")
    print(f"Total items: {result['total_feedback_items']}")
    print(f"Counts by status: {result['counts_by_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
