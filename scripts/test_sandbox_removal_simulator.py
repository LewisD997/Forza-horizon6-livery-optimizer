import json
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.change_plan import make_change_entry, make_optimization_plan
from engine.optimizer.sandbox_removal_simulator import simulate_accepted_candidate_removal
from engine.output.removal_simulation_writer import validate_removal_simulation_report


def main():
    test_no_accepted_candidates()
    test_one_accepted_candidate()
    test_blocked_statuses()
    test_shape_uid_mismatch()
    test_duplicate_accepted_shape_index()
    test_max_removals()
    print("Sandbox removal simulator smoke test passed.")
    return 0


def test_no_accepted_candidates():
    geometry = _geometry()
    original = _clone(geometry)
    plan = _plan(geometry, [1, 2])
    feedback = _feedback(plan, {"C0001": "unsure", "C0002": "rejected"})
    report = simulate_accepted_candidate_removal(geometry, plan, feedback)
    assert report["status"] == "no_accepted_candidates"
    assert report["accepted_candidate_count"] == 0
    assert report["simulated_removed_count"] == 0
    assert report["output_shape_count"] == report["input_shape_count"]
    assert geometry == original
    validate_removal_simulation_report(report)


def test_one_accepted_candidate():
    geometry = _geometry()
    original = _clone(geometry)
    plan = _plan(geometry, [1, 2])
    feedback = _feedback(plan, {"C0001": "accepted", "C0002": "unsure"})
    report = simulate_accepted_candidate_removal(geometry, plan, feedback)
    assert report["status"] == "completed"
    assert report["accepted_candidate_count"] == 1
    assert report["simulated_removed_count"] == 1
    assert report["output_shape_count"] == len(geometry["shapes"]) - 1
    assert report["removed_shapes"][0]["change_id"] == "C0001"
    assert report["removed_shapes"][0]["shape_index"] == 1
    assert report["removed_shapes"][0]["shape_uid"] == plan["changes"][0]["shape_uid"]
    assert geometry == original
    validate_removal_simulation_report(report)


def test_blocked_statuses():
    geometry = _geometry()
    plan = _plan(geometry, [1, 2, 3])
    feedback = _feedback(plan, {"C0001": "protected", "C0002": "rejected", "C0003": "unsure"})
    report = simulate_accepted_candidate_removal(geometry, plan, feedback)
    assert report["simulated_removed_count"] == 0

    conflicting = _feedback(plan, {"C0001": "accepted"})
    conflicting["items"].append({**conflicting["items"][0], "status": "protected"})
    blocked = simulate_accepted_candidate_removal(geometry, plan, conflicting)
    assert blocked["simulated_removed_count"] == 0
    assert any("Protected feedback blocks" in warning for warning in blocked["warnings"])


def test_shape_uid_mismatch():
    geometry = _geometry()
    plan = _plan(geometry, [1])
    feedback = _feedback(plan, {"C0001": "accepted"})
    feedback["items"][0]["shape_uid"] = "wrong"
    report = simulate_accepted_candidate_removal(geometry, plan, feedback)
    assert report["simulated_removed_count"] == 0
    assert report["skipped_candidates"][0]["reason"] == "shape_uid_mismatch"
    assert any("shape_uid" in warning for warning in report["warnings"])


def test_duplicate_accepted_shape_index():
    geometry = _geometry()
    plan = _plan(geometry, [1, 1])
    feedback = _feedback(plan, {"C0001": "accepted", "C0002": "accepted"})
    report = simulate_accepted_candidate_removal(geometry, plan, feedback)
    assert report["simulated_removed_count"] == 1
    assert report["skipped_candidates"][0]["reason"] == "duplicate_shape_index"
    assert any("removing once" in warning for warning in report["warnings"])


def test_max_removals():
    geometry = _geometry()
    plan = _plan(geometry, [1, 2, 3])
    feedback = _feedback(plan, {"C0001": "accepted", "C0002": "accepted", "C0003": "accepted"})
    report = simulate_accepted_candidate_removal(geometry, plan, feedback, options={"max_removals": 2})
    assert report["accepted_candidate_count"] == 3
    assert report["simulated_removed_count"] == 2
    assert report["skipped_candidates"][0]["reason"] == "max_removals_reached"


def _geometry():
    return {
        "shapes": [
            {"type": 1, "data": [0, 0, 200, 160], "color": [245, 245, 245, 255], "score": 0},
            {"type": 16, "data": [50, 50, 12, 8, 0, 0], "color": [255, 0, 0, 128], "score": 0.4},
            {"type": 16, "data": [70, 50, 10, 7, 0, 0], "color": [0, 255, 0, 128], "score": 0.4},
            {"type": 32, "data": [80, 80, 100, 90, 90, 110], "color": [0, 0, 255, 255], "score": 0.5},
        ]
    }


def _plan(geometry, indexes):
    changes = []
    for sequence, shape_index in enumerate(indexes, start=1):
        shape = geometry["shapes"][shape_index]
        changes.append(
            make_change_entry(
                change_id=f"C{sequence:04d}",
                action="mark_candidate",
                shape_index=shape_index,
                shape=shape,
                reason="Fixture candidate.",
                risk_level="review_only",
                status="proposed",
                before=shape,
                after=shape,
                rollback={"action": "none"},
                metadata={"candidate_type": "fixture_candidate", "candidate_score": 0.8},
            )
        )
    return make_optimization_plan(
        input_geometry_path="fixture.json",
        output_geometry_path=None,
        optimization_mode="candidate_plan",
        shape_count_before=len(geometry["shapes"]),
        changes=changes,
        safety_level="non_destructive",
    )


def _feedback(plan, statuses):
    items = []
    for change in plan["changes"]:
        status = statuses.get(change["change_id"], "unsure")
        items.append(
            {
                "change_id": change["change_id"],
                "shape_index": change["shape_index"],
                "shape_uid": change["shape_uid"],
                "candidate_type": (change.get("metadata") or {}).get("candidate_type"),
                "status": status,
                "reviewer_note": "",
                "reviewed_at": None,
                "metadata": {},
            }
        )
    return {"items": items}


def _clone(value):
    return json.loads(json.dumps(value))


if __name__ == "__main__":
    raise SystemExit(main())
