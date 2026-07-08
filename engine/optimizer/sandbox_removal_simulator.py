import copy


SIMULATION_VERSION = "0.6.6"


def simulate_accepted_candidate_removal(
    geometry: dict,
    plan: dict,
    feedback: dict,
    options: dict | None = None,
) -> dict:
    options = options or {}
    original_snapshot = copy.deepcopy(geometry)
    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else []
    sandbox_geometry = copy.deepcopy(geometry)
    sandbox_shapes = sandbox_geometry.get("shapes", [])
    max_removals = options.get("max_removals")
    max_removals = int(max_removals) if max_removals is not None else None

    warnings = []
    removed_shapes = []
    skipped_candidates = []
    remove_indexes = set()
    accepted_candidate_count = 0

    plan_by_id = {
        change.get("change_id"): change
        for change in _candidate_changes(plan)
        if change.get("change_id")
    }
    feedback_by_id, feedback_warnings = _feedback_by_id(feedback)
    warnings.extend(feedback_warnings)

    for change_id, feedback_group in feedback_by_id.items():
        status_info = _resolve_feedback_status(change_id, feedback_group, warnings)
        if status_info["blocked"]:
            if status_info["accepted_requested"]:
                skipped_candidates.append(_skip(change_id, None, "blocked_by_conflicting_or_protected_feedback"))
            continue
        if status_info["status"] != "accepted":
            continue

        accepted_candidate_count += 1
        change = plan_by_id.get(change_id)
        if not change:
            skipped_candidates.append(_skip(change_id, None, "change_id_not_found_in_plan"))
            warnings.append(f"Accepted feedback item {change_id} does not exist in plan.")
            continue

        shape_index = change.get("shape_index")
        if not isinstance(shape_index, int) or shape_index < 0 or shape_index >= len(shapes):
            skipped_candidates.append(_skip(change_id, shape_index, "shape_index_out_of_range"))
            warnings.append(f"Accepted candidate {change_id} has out-of-range shape_index: {shape_index}.")
            continue

        item = feedback_group[0]
        if item.get("shape_uid") != change.get("shape_uid"):
            skipped_candidates.append(_skip(change_id, shape_index, "shape_uid_mismatch"))
            warnings.append(f"Accepted candidate {change_id} shape_uid does not match plan.")
            continue

        if shape_index in remove_indexes:
            skipped_candidates.append(_skip(change_id, shape_index, "duplicate_shape_index"))
            warnings.append(f"Multiple accepted candidates target shape_index {shape_index}; removing once.")
            continue

        if max_removals is not None and len(remove_indexes) >= max(0, max_removals):
            skipped_candidates.append(_skip(change_id, shape_index, "max_removals_reached"))
            warnings.append(f"Max removals reached at {max_removals}; candidate {change_id} skipped.")
            continue

        remove_indexes.add(shape_index)
        removed_shapes.append(
            {
                "change_id": change_id,
                "shape_index": shape_index,
                "shape_uid": change.get("shape_uid"),
                "feedback_status": "accepted",
                "candidate_type": (change.get("metadata") or {}).get("candidate_type"),
                "shape": copy.deepcopy(shapes[shape_index]),
            }
        )

    for index in sorted(remove_indexes, reverse=True):
        del sandbox_shapes[index]

    status = "completed"
    if accepted_candidate_count == 0:
        status = "no_accepted_candidates"
    elif warnings or skipped_candidates:
        status = "completed_with_warnings"

    input_count = len(shapes)
    output_count = len(sandbox_shapes)
    return {
        "simulation_version": SIMULATION_VERSION,
        "status": status,
        "input_shape_count": input_count,
        "accepted_candidate_count": accepted_candidate_count,
        "simulated_removed_count": len(remove_indexes),
        "skipped_count": len(skipped_candidates),
        "output_shape_count": output_count,
        "removed_shapes": removed_shapes,
        "skipped_candidates": skipped_candidates,
        "warnings": warnings,
        "geometry_unchanged_original": geometry == original_snapshot,
        "sandbox_geometry": sandbox_geometry,
    }


def _candidate_changes(plan):
    return [
        change
        for change in plan.get("changes", [])
        if change.get("action") == "mark_candidate"
    ]


def _feedback_by_id(feedback):
    groups = {}
    warnings = []
    for item in feedback.get("items", []) if isinstance(feedback, dict) else []:
        change_id = item.get("change_id")
        if not change_id:
            warnings.append("Feedback item without change_id skipped.")
            continue
        groups.setdefault(change_id, []).append(item)
    for change_id, items in groups.items():
        if len(items) > 1:
            warnings.append(f"Duplicate feedback entries found for {change_id}.")
    return groups, warnings


def _resolve_feedback_status(change_id, items, warnings):
    statuses = [item.get("status") for item in items]
    accepted_requested = "accepted" in statuses
    if "protected" in statuses:
        if accepted_requested:
            warnings.append(f"Protected feedback blocks accepted removal for {change_id}.")
        return {"status": "protected", "blocked": True, "accepted_requested": accepted_requested}
    unique = {status for status in statuses if status}
    if len(unique) > 1:
        warnings.append(f"Conflicting feedback statuses for {change_id}: {sorted(unique)}.")
        return {"status": None, "blocked": True, "accepted_requested": accepted_requested}
    return {
        "status": statuses[0] if statuses else None,
        "blocked": False,
        "accepted_requested": accepted_requested,
    }


def _skip(change_id, shape_index, reason):
    return {
        "change_id": change_id,
        "shape_index": shape_index,
        "reason": reason,
    }
