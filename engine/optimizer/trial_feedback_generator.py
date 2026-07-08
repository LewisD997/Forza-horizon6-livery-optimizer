from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone


TRIAL_VERSION = "0.6.8"
TRIAL_NOTE = "Trial accepted by v0.6.8 workflow; original feedback unchanged."
DEFAULT_CANDIDATE_TYPES = {
    "low_alpha_large_soft_shape",
    "tiny_fragment_cluster_member",
    "ellipse_cluster_member",
}


def generate_trial_feedback(
    plan: dict,
    feedback: dict,
    options: dict | None = None,
) -> dict:
    options = options or {}
    max_trial_accepts = int(options.get("max_trial_accepts", 5))
    explicit_change_ids = _parse_change_ids(options.get("change_ids"))
    allow_review_only = bool(options.get("allow_review_only", False))
    allow_early_shapes = bool(options.get("allow_early_shapes", False))
    candidate_type_filter = options.get("candidate_type")
    risk_level_filter = options.get("risk_level")

    trial_feedback = deepcopy(feedback)
    plan_by_id = _plan_candidates_by_id(plan)
    feedback_by_id = _feedback_items_by_id(trial_feedback)
    selected = []
    skipped = []
    warnings = []

    if explicit_change_ids:
        candidates = [
            _score_candidate(
                change_id,
                plan_by_id.get(change_id),
                feedback_by_id.get(change_id),
                allow_review_only=True,
                allow_early_shapes=True,
                explicit=True,
            )
            for change_id in explicit_change_ids
        ]
    else:
        candidates = [
            _score_candidate(
                change_id,
                change,
                feedback_by_id.get(change_id),
                allow_review_only=allow_review_only,
                allow_early_shapes=allow_early_shapes,
                explicit=False,
            )
            for change_id, change in plan_by_id.items()
        ]

    valid = []
    for candidate in candidates:
        if candidate["skip_reason"]:
            skipped.append(_skip(candidate, candidate["skip_reason"]))
            continue
        if candidate_type_filter and candidate["candidate_type"] != candidate_type_filter:
            skipped.append(_skip(candidate, "candidate_type_filter_mismatch"))
            continue
        if risk_level_filter and candidate["risk_level"] != risk_level_filter:
            skipped.append(_skip(candidate, "risk_level_filter_mismatch"))
            continue
        if not explicit_change_ids and candidate["trial_score"] <= 0:
            skipped.append(_skip(candidate, "non_positive_trial_score"))
            continue
        valid.append(candidate)

    valid.sort(key=lambda item: (item["trial_score"], item["candidate_score"]), reverse=True)
    selected = valid[: max(0, max_trial_accepts)]
    skipped.extend(_skip(candidate, "max_trial_accepts_cap") for candidate in valid[max(0, max_trial_accepts) :])

    now = _now()
    for candidate in selected:
        item = feedback_by_id[candidate["change_id"]]
        item["status"] = "accepted"
        item["reviewer_note"] = TRIAL_NOTE
        item["reviewed_at"] = now
        metadata = item.setdefault("metadata", {})
        metadata["trial_generated"] = True
        metadata["trial_version"] = TRIAL_VERSION
        metadata["trial_reason"] = candidate["trial_reason"]

    trial_feedback["updated_at"] = now
    _refresh_counts(trial_feedback)
    return {
        "trial_feedback": trial_feedback,
        "selected_trial_candidates": [_public_candidate(candidate) for candidate in selected],
        "skipped_candidates": skipped,
        "warnings": warnings,
    }


def _score_candidate(change_id, change, feedback_item, allow_review_only, allow_early_shapes, explicit):
    base = {
        "change_id": change_id,
        "shape_index": None,
        "shape_uid": None,
        "candidate_type": None,
        "risk_level": None,
        "candidate_score": 0.0,
        "trial_score": 0,
        "trial_reason": "",
        "skip_reason": None,
    }
    if not change:
        return {**base, "skip_reason": "change_id_not_found_in_plan"}
    metadata = change.get("metadata") or {}
    item = feedback_item
    base.update(
        {
            "shape_index": change.get("shape_index"),
            "shape_uid": change.get("shape_uid"),
            "candidate_type": metadata.get("candidate_type"),
            "risk_level": change.get("risk_level"),
            "candidate_score": _number(metadata.get("candidate_score")),
        }
    )
    if not item:
        return {**base, "skip_reason": "feedback_item_missing"}
    if item.get("status") in {"protected", "rejected"}:
        return {**base, "skip_reason": f"feedback_status_{item.get('status')}_blocked"}
    if item.get("status") == "accepted" and not explicit:
        return {**base, "skip_reason": "already_accepted_not_selected_by_default"}
    if item.get("status") != "unsure" and not explicit:
        return {**base, "skip_reason": f"feedback_status_{item.get('status')}_not_eligible"}
    if item.get("shape_uid") != change.get("shape_uid"):
        return {**base, "skip_reason": "shape_uid_mismatch"}
    if not metadata.get("candidate_type") or metadata.get("candidate_score") is None:
        return {**base, "skip_reason": "required_candidate_metadata_missing"}

    score = 0
    reasons = []
    risk = change.get("risk_level")
    candidate_type = metadata.get("candidate_type")
    layer_alpha = _number(metadata.get("layer_alpha"), default=None)
    area = _number(metadata.get("layer_area_estimate"), default=None)
    region = metadata.get("region") or {}

    if risk == "low":
        score += 3
        reasons.append("low_risk")
    elif risk == "review_only" and not allow_review_only:
        score -= 5
        reasons.append("review_only_penalty")

    if candidate_type == "tiny_fragment_cluster_member":
        score += 2
        reasons.append("tiny_fragment")
    elif candidate_type == "low_alpha_large_soft_shape" and layer_alpha is not None and layer_alpha <= 0.20:
        score += 2
        reasons.append("very_low_alpha")
    elif candidate_type == "ellipse_cluster_member" and risk == "low":
        score += 1
        reasons.append("low_risk_ellipse_cluster")

    if candidate_type not in DEFAULT_CANDIDATE_TYPES:
        score -= 3
        reasons.append("candidate_type_not_default_conservative")
    if area is not None and area <= 1800:
        score += 1
        reasons.append("small_or_moderate_area")
    if not allow_early_shapes and _number(change.get("shape_index")) < 20:
        score -= 5
        reasons.append("early_shape_penalty")
    if _region_area(region) >= 30000:
        score -= 5
        reasons.append("large_region_penalty")

    if explicit and score <= 0:
        score = 1
        reasons.append("explicit_selection")
    return {
        **base,
        "trial_score": score,
        "trial_reason": ";".join(reasons) if reasons else "eligible",
        "skip_reason": None,
    }


def _plan_candidates_by_id(plan):
    return {
        change.get("change_id"): change
        for change in plan.get("changes", [])
        if change.get("action") == "mark_candidate" and change.get("change_id")
    }


def _feedback_items_by_id(feedback):
    return {item.get("change_id"): item for item in feedback.get("items", []) if item.get("change_id")}


def _refresh_counts(feedback):
    counts = Counter(item.get("status") for item in feedback.get("items", []))
    feedback["total_feedback_items"] = len(feedback.get("items", []))
    feedback["counts_by_status"] = {status: counts.get(status, 0) for status in ("accepted", "protected", "rejected", "unsure")}


def _skip(candidate, reason):
    return {
        "change_id": candidate.get("change_id"),
        "shape_index": candidate.get("shape_index"),
        "candidate_type": candidate.get("candidate_type"),
        "risk_level": candidate.get("risk_level"),
        "reason": reason,
    }


def _public_candidate(candidate):
    return {
        "change_id": candidate["change_id"],
        "shape_index": candidate["shape_index"],
        "shape_uid": candidate["shape_uid"],
        "candidate_type": candidate["candidate_type"],
        "risk_level": candidate["risk_level"],
        "candidate_score": candidate["candidate_score"],
        "trial_score": candidate["trial_score"],
        "trial_reason": candidate["trial_reason"],
    }


def _parse_change_ids(value):
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return list(value)


def _region_area(region):
    if not isinstance(region, dict):
        return 0.0
    return max(0.0, _number(region.get("width"))) * max(0.0, _number(region.get("height")))


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now():
    return datetime.now(timezone.utc).isoformat()
