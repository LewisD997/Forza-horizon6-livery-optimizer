import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.change_plan import make_shape_uid
from engine.optimizer.patch_applier import apply_optimization_plan
from engine.optimizer.plan_generator import generate_noop_plan
from engine.output.optimization_plan_writer import (
    OptimizationPlanError,
    read_optimization_plan,
    validate_optimization_plan,
    write_optimization_plan,
)


def main():
    fixture = ROOT / "test_data" / "paint_studio_source_renderer_fixture.json"
    geometry = json.loads(fixture.read_text(encoding="utf-8"))
    uid_a = make_shape_uid(geometry["shapes"][0], 0)
    uid_b = make_shape_uid(geometry["shapes"][0], 0)
    assert uid_a == uid_b

    noop_plan = generate_noop_plan(geometry, str(fixture), "optimized_geometry.json")
    assert noop_plan["optimization_mode"] == "noop_plan"
    assert noop_plan["proposed_change_count"] == 0
    validate_optimization_plan(noop_plan, geometry=geometry)

    mark_plan = generate_noop_plan(
        geometry,
        str(fixture),
        "optimized_geometry.json",
        include_mark_candidates=True,
        max_mark_candidates=2,
    )
    assert mark_plan["proposed_change_count"] == 2
    validate_optimization_plan(mark_plan, geometry=geometry)
    dry_run = apply_optimization_plan(geometry, mark_plan, dry_run=True)
    assert dry_run["modified_geometry"] == geometry
    assert dry_run["destructive_change_count"] == 0
    assert len(dry_run["ledger"]) == 2

    applied = apply_optimization_plan(geometry, mark_plan, dry_run=False)
    assert applied["modified_geometry"] == geometry
    assert applied["applied_change_count"] == 2

    with tempfile.TemporaryDirectory() as temp_dir:
        plan_path = Path(temp_dir) / "optimization_plan.json"
        write_optimization_plan(mark_plan, plan_path)
        loaded = read_optimization_plan(plan_path)
        assert loaded["changes"][0]["shape_uid"] == mark_plan["changes"][0]["shape_uid"]
        try:
            write_optimization_plan(mark_plan, plan_path)
            raise AssertionError("Expected overwrite protection to reject existing plan.")
        except OptimizationPlanError:
            pass

    print("Optimization plan smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
