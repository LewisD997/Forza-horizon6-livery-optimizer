import copy

from engine.optimizer.change_plan import make_shape_uid


APPLY_PREVIEW_VERSION = "0.6.13"
SUPPORTED_PROPOSAL_VERSIONS = {"0.6.12"}
BLOCKED_GROUPS = {"protect_candidate", "replacement_candidate", "deletion_candidate_review"}


def apply_safe_cleanup_preview(geometry, cleanup_proposal, visible_contribution_report=None, feedback=None, options=None):
    options = options or {}
    original = copy.deepcopy(geometry)
    proposal_copy = copy.deepcopy(cleanup_proposal)
    feedback_copy = copy.deepcopy(feedback or {})
    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else []
    proposed = cleanup_proposal.get("proposed_removals", []) if isinstance(cleanup_proposal, dict) else []
    max_removals = options.get("max_removals")
    warnings = []
    blocked = _proposal_block_reason(cleanup_proposal)
    if blocked:
        warnings.append(blocked)
        return _result("blocked", original, len(shapes), len(proposed), [], [], warnings,
                       geometry != original, (feedback or {}) != feedback_copy, cleanup_proposal != proposal_copy)

    report_by_key = _visible_by_key(visible_contribution_report)
    feedback_by_id = _feedback_by_id(feedback)
    blocked_ids = _blocked_ids(visible_contribution_report)
    valid = []
    skipped = []
    used_indexes = set()
    used_ids = set()
    for entry in proposed:
        checks, reason, evidence = _validate_entry(
            entry, shapes, report_by_key, feedback_by_id, blocked_ids, used_indexes, used_ids,
            visible_contribution_report is not None,
        )
        if reason:
            skipped.append(_skipped(entry, reason, checks))
            continue
        if max_removals is not None and len(valid) >= max(0, int(max_removals)):
            skipped.append(_skipped(entry, "max_removals_reached", checks))
            continue
        index = entry["shape_index"]
        used_indexes.add(index)
        used_ids.add(entry.get("change_id"))
        valid.append({"entry": copy.deepcopy(entry), "shape": copy.deepcopy(shapes[index]), "checks": checks, "evidence": evidence})

    preview = copy.deepcopy(geometry)
    applied = []
    ledger = []
    for order, item in enumerate(sorted(valid, key=lambda value: value["entry"]["shape_index"], reverse=True), 1):
        entry = item["entry"]
        index = entry["shape_index"]
        shape = item["shape"]
        del preview["shapes"][index]
        public = {"change_id": entry.get("change_id"), "shape_index": index, "shape_uid": entry.get("shape_uid"), "reason": entry.get("reason")}
        applied.append(public)
        ledger.append({
            "change_id": entry.get("change_id"), "original_shape_index": index,
            "shape_uid": entry.get("shape_uid"), "shape_type": shape.get("type"),
            "original_shape_data": copy.deepcopy(shape.get("data")),
            "original_shape_color": copy.deepcopy(shape.get("color")),
            "original_shape_score": shape.get("score"),
            "contribution_evidence": copy.deepcopy(item["evidence"]),
            "proposal_reason": entry.get("reason"), "validation_checks": item["checks"],
            "application_status": "applied", "removal_order": order,
            "rollback_payload": {"original_shape_index": index, "shape": copy.deepcopy(shape)},
        })

    status = "no_proposed_removals" if not proposed else "completed"
    if proposed and not applied:
        status = "completed_with_warnings"
    elif skipped or warnings:
        status = "completed_with_warnings"
    return _result(status, preview, len(shapes), len(proposed), applied, skipped, warnings,
                   geometry != original, (feedback or {}) != feedback_copy, cleanup_proposal != proposal_copy, ledger)


def reconstruct_original_from_preview(preview_geometry, application_ledger):
    reconstructed = copy.deepcopy(preview_geometry)
    shapes = reconstructed.setdefault("shapes", [])
    for item in sorted(application_ledger, key=lambda value: value["original_shape_index"]):
        payload = item.get("rollback_payload") or {}
        index = payload.get("original_shape_index")
        shape = payload.get("shape")
        if not isinstance(index, int) or not isinstance(shape, dict) or index < 0 or index > len(shapes):
            raise ValueError(f"Invalid rollback payload for {item.get('change_id')}.")
        shapes.insert(index, copy.deepcopy(shape))
    return reconstructed


def _proposal_block_reason(proposal):
    if not isinstance(proposal, dict): return "cleanup_proposal_not_object"
    if proposal.get("cleanup_proposal_version") not in SUPPORTED_PROPOSAL_VERSIONS: return "unsupported_cleanup_proposal_version"
    if proposal.get("proposal_type") != "safe_delete_pool": return "unsupported_proposal_type"
    if proposal.get("status") != "proposed": return "proposal_status_not_proposed"
    if proposal.get("official_geometry_written") is not False: return "proposal_claims_official_geometry_written"
    if not isinstance(proposal.get("proposed_removals"), list): return "proposed_removals_not_list"
    return None


def _validate_entry(entry, shapes, report_by_key, feedback_by_id, blocked_ids, used_indexes, used_ids, report_required):
    checks = {}
    def check(name, condition, reason):
        checks[name] = bool(condition)
        return None if condition else reason
    index = entry.get("shape_index") if isinstance(entry, dict) else None
    change_id = entry.get("change_id") if isinstance(entry, dict) else None
    for name, condition, reason in (
        ("requires_final_apply", entry.get("requires_final_apply") is True, "requires_final_apply_not_true"),
        ("reason", entry.get("reason") == "zero_or_negligible_visible_contribution", "invalid_proposal_reason"),
        ("shape_index", isinstance(index, int) and 0 <= index < len(shapes), "shape_index_out_of_range"),
        ("duplicate_shape_index", index not in used_indexes, "duplicate_shape_index"),
        ("duplicate_change_id", change_id not in used_ids, "duplicate_change_id"),
        ("not_blocked_group", change_id not in blocked_ids, "listed_in_blocked_review_group"),
        ("feedback", _feedback_status(feedback_by_id, change_id) not in {"protected", "rejected"}, "feedback_protected_or_rejected"),
    ):
        failure = check(name, condition, reason)
        if failure: return checks, failure, None
    expected_uid = make_shape_uid(shapes[index], index)
    failure = check("shape_uid", entry.get("shape_uid") == expected_uid, "shape_uid_mismatch")
    if failure: return checks, failure, None
    evidence = report_by_key.get((change_id, entry.get("shape_uid")))
    if report_required and evidence is None: return {**checks, "visible_report_identity": False}, "visible_report_identity_mismatch", None
    checks["visible_report_identity"] = evidence is not None if report_required else True
    if evidence is not None:
        if evidence.get("contribution_class") != "zero_or_negligible_contribution": return {**checks, "contribution_class": False}, "invalid_contribution_class", evidence
        if evidence.get("recommended_action") != "safe_delete_pool": return {**checks, "recommended_action": False}, "invalid_recommended_action", evidence
        checks.update({"contribution_class": True, "recommended_action": True})
    return checks, None, evidence


def _visible_by_key(report):
    return {(item.get("change_id"), item.get("shape_uid")): item for item in (report or {}).get("results", [])}


def _blocked_ids(report):
    summary = (report or {}).get("summary") or {}
    return {item for group in BLOCKED_GROUPS for item in (summary.get(group) or [])}


def _feedback_by_id(feedback):
    return {item.get("change_id"): item for item in (feedback or {}).get("items", []) if item.get("change_id")}


def _feedback_status(items, change_id):
    return (items.get(change_id) or {}).get("status")


def _skipped(entry, reason, checks):
    return {"change_id": entry.get("change_id"), "shape_index": entry.get("shape_index"), "shape_uid": entry.get("shape_uid"), "reason": reason, "validation_checks": checks}


def _result(status, preview, input_count, candidate_count, applied, skipped, warnings, geometry_changed, feedback_changed, proposal_changed, ledger=None):
    return {
        "apply_preview_version": APPLY_PREVIEW_VERSION, "status": status,
        "input_shape_count": input_count, "proposal_candidate_count": candidate_count,
        "applied_removal_count": len(applied), "skipped_removal_count": len(skipped),
        "output_shape_count": len(preview.get("shapes", [])), "applied_removals": applied,
        "skipped_removals": skipped, "application_ledger": ledger or [], "preview_geometry": preview,
        "warnings": warnings, "safety": {
            "original_geometry_modified": geometry_changed, "original_feedback_modified": feedback_changed,
            "input_proposal_modified": proposal_changed, "output_is_preview_only": True,
            "official_cleanup_output_written": False, "rollback_information_available": True,
        },
    }
