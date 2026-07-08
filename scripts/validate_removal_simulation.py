import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.output.removal_simulation_writer import validate_removal_simulation_report


def main():
    parser = argparse.ArgumentParser(description="Validate removal_simulation_report.json.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--geometry", required=True)
    args = parser.parse_args()

    try:
        result = validate_report(Path(args.report), Path(args.geometry))
    except Exception as exc:
        print(f"Removal simulation validation failed: {exc}", file=sys.stderr)
        return 1

    print("Removal simulation validation passed.")
    print(f"Status: {result['status']}")
    print(f"Input shapes: {result['input_shape_count']}")
    print(f"Output shapes: {result['output_shape_count']}")
    print(f"Simulated removed: {result['simulated_removed_count']}")
    return 0


def validate_report(report_path: Path, geometry_path: Path):
    report = _load_json(report_path)
    geometry = _load_json(geometry_path)
    validate_removal_simulation_report(report)

    safety = report.get("safety") or {}
    if safety.get("original_geometry_modified") is not False:
        raise ValueError("Report must state original_geometry_modified is false.")
    if report["input_shape_count"] != len(geometry.get("shapes", [])):
        raise ValueError("Report input_shape_count does not match original geometry.")
    if report["status"] == "no_accepted_candidates" and report["simulated_removed_count"] != 0:
        raise ValueError("No accepted candidates must remove zero shapes.")
    removed_indexes = [item.get("shape_index") for item in report.get("removed_shapes", [])]
    if len(removed_indexes) != len(set(removed_indexes)):
        raise ValueError("Removed shape indexes must be unique.")
    for item in report.get("removed_shapes", []):
        if item.get("feedback_status") != "accepted":
            raise ValueError("Removed shapes must only come from accepted feedback.")

    sandbox_path = (report.get("outputs") or {}).get("sandbox_geometry")
    if sandbox_path:
        sandbox = _load_json(Path(sandbox_path))
        if len(sandbox.get("shapes", [])) != report["output_shape_count"]:
            raise ValueError("Sandbox geometry shape count does not match report.")
    return report


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
