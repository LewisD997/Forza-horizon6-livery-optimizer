import copy
import json
from collections import Counter
from pathlib import Path


class TrialFeedbackWriteError(Exception):
    pass


def write_trial_feedback(result, feedback_path, report_path, overwrite=False):
    trial_feedback = result.get("trial_feedback")
    if not isinstance(trial_feedback, dict):
        raise TrialFeedbackWriteError("Trial result missing trial_feedback.")
    feedback_output = Path(feedback_path)
    report_output = Path(report_path)
    if feedback_output.exists() and not overwrite:
        raise TrialFeedbackWriteError(f"Trial feedback already exists: {feedback_output}")
    if report_output.exists() and not overwrite:
        raise TrialFeedbackWriteError(f"Trial feedback report already exists: {report_output}")
    feedback_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    feedback_output.write_text(json.dumps(trial_feedback, indent=2, ensure_ascii=False), encoding="utf-8")
    report = copy.deepcopy(result)
    report.pop("trial_feedback", None)
    report_output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"trial_feedback": str(feedback_output), "trial_feedback_report": str(report_output)}


def validate_trial_feedback(trial_feedback, original_feedback, plan):
    if not isinstance(trial_feedback, dict) or not isinstance(original_feedback, dict):
        raise TrialFeedbackWriteError("Feedback documents must be objects.")
    original_items = original_feedback.get("items", [])
    trial_items = trial_feedback.get("items", [])
    if len(original_items) != len(trial_items):
        raise TrialFeedbackWriteError("Original and trial feedback item counts differ.")
    plan_ids = {
        change.get("change_id")
        for change in plan.get("changes", [])
        if change.get("action") == "mark_candidate"
    }
    original_by_id = {item.get("change_id"): item for item in original_items}
    accepted_changes = []
    for item in trial_items:
        change_id = item.get("change_id")
        if change_id not in plan_ids:
            raise TrialFeedbackWriteError(f"Trial feedback change_id not found in plan: {change_id}")
        original = original_by_id.get(change_id)
        if not original:
            raise TrialFeedbackWriteError(f"Trial feedback item missing in original: {change_id}")
        if original.get("status") in {"protected", "rejected"} and item.get("status") == "accepted":
            raise TrialFeedbackWriteError(f"Protected/rejected item became accepted: {change_id}")
        if original.get("status") != item.get("status"):
            if not (original.get("status") == "unsure" and item.get("status") == "accepted"):
                raise TrialFeedbackWriteError(f"Unexpected status change for {change_id}.")
            accepted_changes.append(change_id)
    expected = _counts(trial_items)
    if trial_feedback.get("counts_by_status") != expected:
        raise TrialFeedbackWriteError("Trial feedback counts_by_status is inconsistent.")
    return {
        "valid": True,
        "accepted_change_ids": accepted_changes,
        "counts_by_status": expected,
    }


def _counts(items):
    counts = Counter(item.get("status") for item in items)
    return {status: counts.get(status, 0) for status in ("accepted", "protected", "rejected", "unsure")}
