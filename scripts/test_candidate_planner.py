import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_planner import generate_cleanup_candidate_plan
from engine.optimizer.patch_applier import apply_optimization_plan
from engine.output.optimization_plan_writer import validate_optimization_plan


def main():
    geometry = _fixture_geometry()
    original = json.loads(json.dumps(geometry))
    report = {
        "image_info": {"size": {"width": 200, "height": 160}},
        "visual_diff": {
            "high_difference_regions": [
                {"x": 110, "y": 20, "width": 60, "height": 60, "difference_score": 0.72}
            ]
        },
    }

    plan = generate_cleanup_candidate_plan(
        geometry,
        report,
        options={"input_geometry_path": "fixture.json", "output_geometry_path": "optimized.json"},
    )
    assert geometry == original
    assert plan["optimization_mode"] == "candidate_plan"
    assert plan["safety_level"] == "non_destructive"
    assert plan["proposed_change_count"] > 0
    validate_optimization_plan(plan, geometry=geometry)
    assert all(change["action"] == "mark_candidate" for change in plan["changes"])
    assert all(change["risk_level"] in {"review_only", "low"} for change in plan["changes"])

    capped = generate_cleanup_candidate_plan(geometry, report, options={"max_candidates": 2})
    assert capped["proposed_change_count"] == 2

    strict = generate_cleanup_candidate_plan(geometry, report, options={"min_candidate_score": 0.95})
    assert strict["proposed_change_count"] == 0

    dry_run = apply_optimization_plan(geometry, plan, dry_run=True)
    assert dry_run["modified_geometry"] == geometry
    assert dry_run["destructive_change_count"] == 0

    summary = plan["candidate_summary"]
    assert summary["non_destructive"] is True
    assert summary["total_candidates"] == plan["proposed_change_count"]
    assert summary["candidate_counts_by_type"]

    print("Cleanup candidate planner smoke test passed.")
    return 0


def _fixture_geometry():
    shapes = [
        {"type": 1, "data": [0, 0, 200, 160], "color": [240, 240, 240, 255], "score": 0},
        {"type": 16, "data": [40, 40, 24, 18, 0, 0], "color": [120, 120, 255, 90], "score": 0.7},
        {"type": 16, "data": [120, 50, 8, 6, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
        {"type": 16, "data": [124, 52, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
        {"type": 16, "data": [128, 54, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
        {"type": 16, "data": [132, 56, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
        {"type": 16, "data": [136, 58, 7, 5, 0, 0], "color": [255, 80, 80, 180], "score": 0.5},
    ]
    duplicate = {"type": 2, "data": [160, 120, 3, 3, 0, 0], "color": [20, 20, 20, 255], "score": 0.2}
    shapes.append(duplicate)
    shapes.append(json.loads(json.dumps(duplicate)))
    return {"shapes": shapes}


if __name__ == "__main__":
    raise SystemExit(main())
