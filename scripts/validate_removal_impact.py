import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.output.removal_impact_writer import validate_removal_impact_report


def main():
    parser = argparse.ArgumentParser(description="Validate removal_impact_report.json.")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    try:
        report = _load_json(Path(args.report))
        validate_removal_impact_report(report)
    except Exception as exc:
        print(f"Removal impact validation failed: {exc}", file=sys.stderr)
        return 1

    print("Removal impact validation passed.")
    print(f"Status: {report['status']}")
    print(f"Overall decision: {report['overall_decision']}")
    print(f"Simulated removed: {report['shape_counts']['simulated_removed_count']}")
    return 0


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Impact report not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
