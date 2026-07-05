import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.optimizer.candidate_feedback import (
    CandidateFeedbackError,
    create_feedback_template,
    update_feedback_status,
    validate_candidate_feedback,
)
from engine.optimizer.candidate_planner import generate_cleanup_candidate_plan
from engine.output.candidate_feedback_writer import (
    export_feedback_csv,
    read_candidate_feedback,
    write_candidate_feedback,
)


def main():
    geometry = _fixture_geometry()
    original = json.loads(json.dumps(geometry))
    plan = generate_cleanup_candidate_plan(
        geometry,
        {"image_info": {"size": {"width": 200, "height": 160}}},
        options={"input_geometry_path": "fixture.json", "max_candidates": 10},
    )
    feedback = create_feedback_template(plan)
    assert feedback["total_feedback_items"] >= 4
    assert feedback["total_feedback_items"] == plan["proposed_change_count"]
    assert feedback["counts_by_status"]["unsure"] == feedback["total_feedback_items"]
    validate_candidate_feedback(feedback, plan=plan)

    first_id = feedback["items"][0]["change_id"]
    feedback = update_feedback_status(feedback, first_id, "accepted", "Looks safe in fixture.")
    feedback = update_feedback_status(feedback, feedback["items"][1]["change_id"], "rejected", "Important shape.")
    feedback = update_feedback_status(feedback, feedback["items"][2]["change_id"], "protected", "Never remove.")
    feedback = update_feedback_status(feedback, feedback["items"][3]["change_id"], "unsure", "Needs another look.")
    validate_candidate_feedback(feedback, plan=plan)
    assert feedback["counts_by_status"]["accepted"] == 1
    assert feedback["counts_by_status"]["rejected"] == 1
    assert feedback["counts_by_status"]["protected"] == 1

    try:
        update_feedback_status(feedback, first_id, "bad_status")
        raise AssertionError("Expected invalid status rejection.")
    except CandidateFeedbackError:
        pass

    with tempfile.TemporaryDirectory() as temp_dir:
        feedback_path = Path(temp_dir) / "candidate_feedback.json"
        csv_path = Path(temp_dir) / "candidate_feedback.csv"
        write_candidate_feedback(feedback, feedback_path)
        loaded = read_candidate_feedback(feedback_path)
        assert loaded["counts_by_status"] == feedback["counts_by_status"]
        export_feedback_csv(loaded, csv_path)
        assert csv_path.exists()

    assert geometry == original
    print("Candidate feedback smoke test passed.")
    return 0


def _fixture_geometry():
    return {
        "shapes": [
            {"type": 1, "data": [0, 0, 200, 160], "color": [245, 245, 245, 255], "score": 0},
            {"type": 16, "data": [54, 44, 26, 18, 0, 0], "color": [120, 120, 255, 80], "score": 0.7},
            {"type": 16, "data": [86, 44, 14, 10, 0, 0], "color": [120, 120, 255, 90], "score": 0.6},
            {"type": 16, "data": [118, 44, 12, 9, 0, 0], "color": [120, 120, 255, 100], "score": 0.6},
            {"type": 16, "data": [150, 44, 11, 9, 0, 0], "color": [120, 120, 255, 100], "score": 0.6},
            {"type": 1, "data": [40, 110, 8, 6], "color": [245, 245, 245, 255], "score": 0.4},
            {"type": 1, "data": [40, 110, 8, 6], "color": [245, 245, 245, 255], "score": 0.4},
        ]
    }


if __name__ == "__main__":
    raise SystemExit(main())
