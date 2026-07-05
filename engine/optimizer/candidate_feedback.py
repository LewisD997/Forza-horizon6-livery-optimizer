from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone


FEEDBACK_VERSION = "0.6.4"
FEEDBACK_STATUSES = {"accepted", "rejected", "unsure", "protected"}


class CandidateFeedbackError(Exception):
    pass


def create_feedback_template(plan: dict) -> dict:
    items = []
    for change in _candidate_changes(plan):
        metadata = change.get("metadata") or {}
        items.append(
            {
                "change_id": change.get("change_id"),
                "shape_index": change.get("shape_index"),
                "shape_uid": change.get("shape_uid"),
                "candidate_type": metadata.get("candidate_type"),
                "status": "unsure",
                "reviewer_note": "",
                "reviewed_at": None,
                "metadata": {
                    "candidate_score": metadata.get("candidate_score"),
                    "risk_level": change.get("risk_level"),
                },
            }
        )
    now = _now()
    feedback = {
        "feedback_version": FEEDBACK_VERSION,
        "source_plan_path": plan.get("input_geometry_path") or "",
        "created_at": now,
        "updated_at": now,
        "total_feedback_items": len(items),
        "counts_by_status": {},
        "items": items,
    }
    return _refresh_counts(feedback)


def update_feedback_status(
    feedback: dict,
    change_id: str,
    status: str,
    reviewer_note: str | None = None,
) -> dict:
    if status not in FEEDBACK_STATUSES:
        raise CandidateFeedbackError(f"Invalid feedback status: {status}")
    updated = deepcopy(feedback)
    for item in updated.get("items", []):
        if item.get("change_id") == change_id:
            item["status"] = status
            if reviewer_note is not None:
                item["reviewer_note"] = reviewer_note
            item["reviewed_at"] = _now()
            updated["updated_at"] = item["reviewed_at"]
            return _refresh_counts(updated)
    raise CandidateFeedbackError(f"Feedback item not found: {change_id}")


def validate_candidate_feedback(feedback: dict, plan: dict | None = None) -> dict:
    if not isinstance(feedback, dict):
        raise CandidateFeedbackError("Candidate feedback must be an object.")
    required = {
        "feedback_version",
        "source_plan_path",
        "created_at",
        "updated_at",
        "total_feedback_items",
        "counts_by_status",
        "items",
    }
    missing = sorted(required - set(feedback))
    if missing:
        raise CandidateFeedbackError(f"Feedback missing required fields: {missing}")
    items = feedback.get("items")
    if not isinstance(items, list):
        raise CandidateFeedbackError("Feedback items must be a list.")
    if feedback.get("total_feedback_items") != len(items):
        raise CandidateFeedbackError("total_feedback_items does not match items length.")

    plan_by_id = {}
    if plan is not None:
        plan_by_id = {change.get("change_id"): change for change in _candidate_changes(plan)}

    for index, item in enumerate(items):
        _validate_item(item, index, plan_by_id)

    expected = _count_statuses(items)
    if feedback.get("counts_by_status") != expected:
        raise CandidateFeedbackError("counts_by_status is not consistent with items.")
    return {
        "valid": True,
        "total_feedback_items": len(items),
        "counts_by_status": expected,
    }


def summarize_candidate_feedback(feedback: dict) -> dict:
    items = feedback.get("items", [])
    grouped = {status: [] for status in sorted(FEEDBACK_STATUSES)}
    for item in items:
        grouped.setdefault(item.get("status"), []).append(item)
    return {
        "total_feedback_items": len(items),
        "counts_by_status": _count_statuses(items),
        "accepted": grouped.get("accepted", []),
        "rejected": grouped.get("rejected", []),
        "protected": grouped.get("protected", []),
        "unsure": grouped.get("unsure", []),
        "warnings": [],
    }


def _candidate_changes(plan):
    return [
        change
        for change in plan.get("changes", [])
        if change.get("action") == "mark_candidate"
    ]


def _validate_item(item, index, plan_by_id):
    required = {
        "change_id",
        "shape_index",
        "shape_uid",
        "candidate_type",
        "status",
        "reviewer_note",
        "reviewed_at",
        "metadata",
    }
    if not isinstance(item, dict):
        raise CandidateFeedbackError(f"Feedback item {index} must be an object.")
    missing = sorted(required - set(item))
    if missing:
        raise CandidateFeedbackError(f"Feedback item {index} missing fields: {missing}")
    if item.get("status") not in FEEDBACK_STATUSES:
        raise CandidateFeedbackError(f"Feedback item {index} has invalid status.")
    if plan_by_id:
        change = plan_by_id.get(item.get("change_id"))
        if not change:
            raise CandidateFeedbackError(f"Feedback item {index} change_id is not in plan.")
        if item.get("shape_uid") != change.get("shape_uid"):
            raise CandidateFeedbackError(f"Feedback item {index} shape_uid does not match plan.")


def _refresh_counts(feedback):
    feedback["total_feedback_items"] = len(feedback.get("items", []))
    feedback["counts_by_status"] = _count_statuses(feedback.get("items", []))
    return feedback


def _count_statuses(items):
    counts = Counter(item.get("status") for item in items)
    return {status: counts.get(status, 0) for status in sorted(FEEDBACK_STATUSES)}


def _now():
    return datetime.now(timezone.utc).isoformat()
