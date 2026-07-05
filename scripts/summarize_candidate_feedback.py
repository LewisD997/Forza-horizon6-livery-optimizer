import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_feedback import summarize_candidate_feedback
from engine.output.candidate_feedback_writer import read_candidate_feedback


def main():
    parser = argparse.ArgumentParser(description="Summarize candidate feedback.")
    parser.add_argument("--feedback", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    feedback = read_candidate_feedback(args.feedback)
    summary = summarize_candidate_feedback(feedback)
    lines = [
        "Candidate Feedback Summary",
        f"Total items: {summary['total_feedback_items']}",
        f"Counts by status: {summary['counts_by_status']}",
        f"Accepted: {len(summary['accepted'])}",
        f"Rejected: {len(summary['rejected'])}",
        f"Protected: {len(summary['protected'])}",
        f"Unsure: {len(summary['unsure'])}",
    ]
    text = "\n".join(lines)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
