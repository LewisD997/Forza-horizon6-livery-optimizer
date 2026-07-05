import csv
import json
from pathlib import Path

from engine.optimizer.candidate_feedback import validate_candidate_feedback


class CandidateFeedbackWriteError(Exception):
    pass


def write_candidate_feedback(feedback, path, overwrite=False):
    validate_candidate_feedback(feedback)
    feedback_path = Path(path)
    if feedback_path.exists() and not overwrite:
        raise CandidateFeedbackWriteError(f"Candidate feedback already exists: {feedback_path}")
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_path.write_text(json.dumps(feedback, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"feedback_path": str(feedback_path), "total_feedback_items": feedback["total_feedback_items"]}


def read_candidate_feedback(path):
    feedback_path = Path(path)
    try:
        feedback = json.loads(feedback_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CandidateFeedbackWriteError(f"Invalid candidate feedback JSON: {feedback_path}") from exc
    validate_candidate_feedback(feedback)
    return feedback


def export_feedback_csv(feedback, path):
    validate_candidate_feedback(feedback)
    rows = []
    for item in feedback.get("items", []):
        metadata = item.get("metadata") or {}
        rows.append(
            {
                "change_id": item.get("change_id"),
                "shape_index": item.get("shape_index"),
                "shape_uid": item.get("shape_uid"),
                "candidate_type": item.get("candidate_type"),
                "status": item.get("status"),
                "reviewer_note": item.get("reviewer_note"),
                "reviewed_at": item.get("reviewed_at"),
                "candidate_score": metadata.get("candidate_score"),
                "risk_level": metadata.get("risk_level"),
            }
        )
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "change_id",
        "shape_index",
        "shape_uid",
        "candidate_type",
        "status",
        "reviewer_note",
        "reviewed_at",
        "candidate_score",
        "risk_level",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(csv_path)
