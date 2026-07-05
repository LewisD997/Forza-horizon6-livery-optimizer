import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_feedback import update_feedback_status
from engine.output.candidate_feedback_writer import (
    export_feedback_csv,
    read_candidate_feedback,
    write_candidate_feedback,
)


def main():
    parser = argparse.ArgumentParser(description="Update one candidate feedback item.")
    parser.add_argument("--feedback", required=True)
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--status", required=True, choices=("accepted", "rejected", "unsure", "protected"))
    parser.add_argument("--note", default=None)
    args = parser.parse_args()

    feedback_path = Path(args.feedback)
    feedback = read_candidate_feedback(feedback_path)
    updated = update_feedback_status(feedback, args.change_id, args.status, args.note)
    write_candidate_feedback(updated, feedback_path, overwrite=True)
    export_feedback_csv(updated, feedback_path.with_suffix(".csv"))
    print(f"Updated {args.change_id} -> {args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
