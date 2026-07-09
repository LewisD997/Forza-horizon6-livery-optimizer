TRIAGE_VERSION = "0.6.10"

VALID_TRIAGE_DECISIONS = {
    "safe_delete_candidate",
    "visible_but_minor",
    "needs_replacement",
    "protect_candidate",
    "unclear_needs_review",
}


DEFAULT_THRESHOLDS = {
    "very_low_global_change": 0.0005,
    "low_global_change": 0.001,
    "moderate_global_change": 0.003,
    "low_local_change": 0.03,
    "moderate_local_change": 0.10,
    "very_high_local_change": 0.30,
}


def triage_ablation_result(result: dict, options: dict | None = None) -> dict:
    options = options or {}
    thresholds = {**DEFAULT_THRESHOLDS, **(options.get("thresholds") or {})}
    impact = result.get("impact") or {}
    change_id = result.get("change_id")
    candidate_type = result.get("candidate_type")
    status = impact.get("status")
    decision = impact.get("overall_decision")
    global_ratio = _number(impact.get("changed_pixel_ratio"), None)
    local_ratio = _number(impact.get("local_changed_pixel_ratio"), None)
    reasons = []

    if status != "completed":
        return _triage(
            change_id,
            "unclear_needs_review",
            0.35,
            ["impact_scoring_not_completed"],
            "Review inputs and regenerate evidence before deciding.",
        )

    if global_ratio is None or local_ratio is None:
        return _triage(
            change_id,
            "unclear_needs_review",
            0.35,
            ["missing_global_or_local_metric"],
            "Review the evidence card manually.",
        )

    if global_ratio <= thresholds["very_low_global_change"]:
        reasons.append("very_low_global_change")
    elif global_ratio <= thresholds["low_global_change"]:
        reasons.append("low_global_change")
    elif global_ratio <= thresholds["moderate_global_change"]:
        reasons.append("moderate_global_change")
    else:
        reasons.append("high_global_change")

    if local_ratio <= thresholds["low_local_change"]:
        reasons.append("low_local_change")
    elif local_ratio <= thresholds["moderate_local_change"]:
        reasons.append("moderate_local_change")
    elif local_ratio <= thresholds["very_high_local_change"]:
        reasons.append("high_local_change")
    else:
        reasons.append("very_high_local_change")

    if local_ratio > thresholds["very_high_local_change"]:
        return _triage(
            change_id,
            "protect_candidate",
            0.82,
            reasons + ["local_change_too_large"],
            "Keep this candidate protected until a human reviews replacement strategy.",
        )

    if candidate_type == "low_alpha_large_soft_shape" and local_ratio > thresholds["low_local_change"]:
        return _triage(
            change_id,
            "needs_replacement",
            0.74 if local_ratio > thresholds["moderate_local_change"] else 0.62,
            reasons + ["low_alpha_soft_shape_has_visible_local_change"],
            "Do not delete directly; consider replacement or local redraw later.",
        )

    if decision == "safe_to_remove" and local_ratio <= thresholds["low_local_change"]:
        return _triage(
            change_id,
            "safe_delete_candidate",
            0.86,
            reasons + ["impact_decision_safe"],
            "Candidate can be considered for future delete proposal, still requiring review.",
        )

    if (
        candidate_type == "tiny_fragment_cluster_member"
        and global_ratio <= thresholds["low_global_change"]
        and local_ratio <= thresholds["low_local_change"]
    ):
        return _triage(
            change_id,
            "safe_delete_candidate",
            0.78,
            reasons + ["tiny_fragment_with_tiny_visual_change"],
            "Candidate is a good future delete proposal if the review card agrees.",
        )

    if global_ratio <= thresholds["low_global_change"] and local_ratio <= thresholds["moderate_local_change"]:
        triage_decision = "visible_but_minor" if decision != "risky" else "unclear_needs_review"
        return _triage(
            change_id,
            triage_decision,
            0.58 if triage_decision == "unclear_needs_review" else 0.68,
            reasons + ["small_global_change_but_visible_local_change"],
            "Inspect evidence card before deciding whether this is acceptable.",
        )

    if global_ratio <= thresholds["moderate_global_change"] and local_ratio > thresholds["moderate_local_change"]:
        return _triage(
            change_id,
            "needs_replacement",
            0.70,
            reasons + ["localized_change_is_visible"],
            "Treat as a replacement candidate rather than a direct deletion.",
        )

    return _triage(
        change_id,
        "unclear_needs_review",
        0.45,
        reasons + ["rule_boundary_case"],
        "Review evidence manually before assigning delete, replace, or protect.",
    )


def _triage(change_id, decision, confidence, reasons, action):
    return {
        "change_id": change_id,
        "triage_decision": decision,
        "triage_confidence": round(max(0.0, min(1.0, float(confidence))), 3),
        "triage_reasons": reasons,
        "recommended_next_action": action,
        "delete_allowed": decision == "safe_delete_candidate",
        "replacement_candidate": decision == "needs_replacement",
        "protect_recommended": decision == "protect_candidate",
    }


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
