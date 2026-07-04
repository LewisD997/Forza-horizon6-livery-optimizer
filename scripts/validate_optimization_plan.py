import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.output.optimization_plan_writer import (
    OptimizationPlanError,
    read_optimization_plan,
    validate_optimization_plan,
)


def main():
    parser = argparse.ArgumentParser(description="Validate a FLO optimization plan / patch ledger.")
    parser.add_argument("--plan", required=True, help="Optimization plan JSON path.")
    parser.add_argument("--geometry", help="Paint Studio geometry JSON path for shape_uid validation.")
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="Allow destructive actions during validation. Off by default.",
    )
    args = parser.parse_args()

    try:
        geometry = _load_geometry(Path(args.geometry)) if args.geometry else None
        plan = read_optimization_plan(args.plan)
        validate_optimization_plan(plan, geometry=geometry, allow_destructive=args.allow_destructive)
    except (OSError, ValueError, OptimizationPlanError) as exc:
        print(f"Optimization plan validation failed: {exc}", file=sys.stderr)
        return 1

    print("Optimization plan validation passed.")
    print(f"Plan version: {plan['plan_version']}")
    print(f"Proposed changes: {plan['proposed_change_count']}")
    print(f"Applied changes: {plan['applied_change_count']}")
    return 0


def _load_geometry(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid geometry JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
        raise ValueError(f"Geometry must contain a top-level shapes list: {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
