import copy
import json
from pathlib import Path

from engine.optimizer.removal_impact_scorer import score_removal_impact
from engine.optimizer.sandbox_removal_simulator import simulate_accepted_candidate_removal
from engine.output.removal_impact_writer import write_removal_impact_report
from engine.output.removal_simulation_writer import write_removal_simulation_report, write_sandbox_geometry
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview
from engine.vision.visual_diff import compare_images


ABLATION_VERSION = "0.6.9"
VALID_DECISIONS = {"safe_to_remove", "probably_safe", "risky", "failed", "not_applicable"}


def run_per_candidate_ablation(
    geometry: dict,
    plan: dict,
    feedback: dict,
    candidates: list[dict],
    options: dict | None = None,
) -> dict:
    options = options or {}
    original_geometry = copy.deepcopy(geometry)
    original_feedback = copy.deepcopy(feedback)
    output_dir = Path(options.get("output_dir", "removal_simulation/ablation"))
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    results = []

    plan_by_id = _plan_by_id(plan)
    feedback_by_id = _feedback_by_id(feedback)
    ordered_candidates = _dedupe_candidates(candidates)

    for candidate in ordered_candidates:
        result = _run_one_candidate(
            geometry,
            plan,
            feedback,
            candidate,
            plan_by_id,
            feedback_by_id,
            options,
            output_dir,
        )
        results.append(result)
        warnings.extend(result.get("warnings", []))

    status = "completed"
    if not ordered_candidates:
        status = "no_candidates"
    elif warnings or any(item["impact"]["overall_decision"] == "failed" for item in results):
        status = "completed_with_warnings"

    report = {
        "ablation_version": ABLATION_VERSION,
        "status": status,
        "input_paths": {
            "geometry": _path_string(options.get("geometry_path")),
            "plan": _path_string(options.get("plan_path")),
            "feedback": _path_string(options.get("feedback_path")),
            "trial_report": _path_string(options.get("trial_report_path")),
        },
        "output_dir": str(output_dir),
        "candidate_count": len(ordered_candidates),
        "results": results,
        "summary": _summary(results),
        "batch_reference": _batch_reference(options.get("trial_report")),
        "safety": {
            "original_geometry_modified": geometry != original_geometry,
            "original_feedback_modified": feedback != original_feedback,
            "official_cleanup_output_written": False,
            "sandbox_only": True,
        },
        "warnings": warnings,
    }
    return report


def _run_one_candidate(geometry, plan, feedback, candidate, plan_by_id, feedback_by_id, options, output_dir):
    change_id = candidate.get("change_id")
    candidate_dir = output_dir / "candidates" / _safe_name(change_id or "missing_change_id")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    outputs = _candidate_outputs(candidate_dir)
    warnings = []
    change = plan_by_id.get(change_id)
    feedback_item = feedback_by_id.get(change_id)
    base = _result_base(candidate, change, outputs)

    if not change:
        warnings.append(f"Candidate {change_id} skipped: change_id not found in plan.")
        return _skipped_result(base, "change_id_not_found_in_plan", warnings)
    if not feedback_item:
        warnings.append(f"Candidate {change_id} skipped: feedback item missing.")
        return _skipped_result(base, "feedback_item_missing", warnings)
    if feedback_item.get("status") in {"protected", "rejected"}:
        warnings.append(f"Candidate {change_id} skipped: feedback status {feedback_item.get('status')} is blocked.")
        return _skipped_result(base, f"feedback_status_{feedback_item.get('status')}_blocked", warnings)
    if feedback_item.get("shape_uid") != change.get("shape_uid"):
        warnings.append(f"Candidate {change_id} skipped: shape_uid mismatch.")
        return _skipped_result(base, "shape_uid_mismatch", warnings)

    single_feedback = _single_candidate_feedback(feedback, change_id)
    _write_json(single_feedback, outputs["candidate_feedback"], options.get("overwrite", False))
    removal = simulate_accepted_candidate_removal(geometry, plan, single_feedback)
    removal.update(
        {
            "input_geometry_path": _path_string(options.get("geometry_path")),
            "plan_path": _path_string(options.get("plan_path")),
            "feedback_path": outputs["candidate_feedback"],
            "output_dir": str(candidate_dir),
            "outputs": {
                "sandbox_geometry": None,
                "before_preview": None,
                "after_preview": None,
                "diff": None,
                "summary": None,
                "report": outputs["removal_report"],
            },
            "safety": {
                "original_geometry_modified": not removal["geometry_unchanged_original"],
                "only_accepted_candidates_considered": True,
                "protected_candidates_blocked": True,
                "rejected_candidates_blocked": True,
                "unsure_candidates_blocked": True,
            },
        }
    )
    if removal["simulated_removed_count"] == 1:
        removal["outputs"]["sandbox_geometry"] = write_sandbox_geometry(
            removal["sandbox_geometry"],
            outputs["sandbox_geometry"],
            overwrite=options.get("overwrite", False),
        )
        _render_candidate_outputs(removal, options, outputs)
    else:
        removal["warnings"].append("Candidate did not remove exactly one shape in sandbox.")

    if removal["status"] == "completed" and removal.get("warnings"):
        removal["status"] = "completed_with_warnings"
    write_removal_simulation_report(removal, outputs["removal_report"], overwrite=options.get("overwrite", False))

    impact = score_removal_impact(
        removal["outputs"].get("before_preview"),
        removal["outputs"].get("after_preview"),
        removal_report=removal,
        plan=plan,
        feedback=single_feedback,
        options=_impact_options(options),
    )
    impact["input_paths"]["removal_simulation_report"] = outputs["removal_report"]
    write_removal_impact_report(impact, outputs["impact_report"], overwrite=options.get("overwrite", False))

    warnings.extend(removal.get("warnings", []))
    warnings.extend(impact.get("warnings", []))
    return {
        **base,
        "removal": {
            "status": removal.get("status"),
            "simulated_removed_count": removal.get("simulated_removed_count"),
            "input_shape_count": removal.get("input_shape_count"),
            "output_shape_count": removal.get("output_shape_count"),
        },
        "impact": _impact_summary(impact),
        "outputs": outputs,
        "warnings": warnings,
    }


def _single_candidate_feedback(feedback, selected_change_id):
    single = copy.deepcopy(feedback)
    for item in single.get("items", []):
        if item.get("change_id") == selected_change_id:
            item["status"] = "accepted"
            item["reviewer_note"] = "Single-candidate ablation accepted by v0.6.9; original feedback unchanged."
            metadata = item.setdefault("metadata", {})
            metadata["single_candidate_ablation"] = True
            metadata["ablation_version"] = ABLATION_VERSION
        elif item.get("status") == "accepted":
            item["status"] = "unsure"
            metadata = item.setdefault("metadata", {})
            metadata["single_candidate_ablation_temporarily_unaccepted"] = True
    _refresh_counts(single)
    return single


def _render_candidate_outputs(removal, options, outputs):
    geometry_path = options.get("geometry_path")
    sandbox_path = outputs["sandbox_geometry"]
    if not geometry_path or not sandbox_path:
        removal["warnings"].append("Preview rendering skipped because geometry paths are missing.")
        return
    width, height = _image_size(options.get("source_image_path"))
    before = render_paint_studio_preview(
        str(geometry_path),
        outputs["before_preview"],
        width=width,
        height=height,
        ssaa=int(options.get("ssaa", 2)),
        export_mode="full_canvas_opaque",
    )
    after = render_paint_studio_preview(
        str(sandbox_path),
        outputs["after_preview"],
        width=width,
        height=height,
        ssaa=int(options.get("ssaa", 2)),
        export_mode="full_canvas_opaque",
    )
    compare_images(outputs["before_preview"], outputs["after_preview"], outputs["diff"])
    removal["outputs"]["before_preview"] = outputs["before_preview"]
    removal["outputs"]["after_preview"] = outputs["after_preview"]
    removal["outputs"]["diff"] = outputs["diff"]
    removal["render_metadata"] = {"before": before, "after": after}


def _skipped_result(base, reason, warnings):
    return {
        **base,
        "removal": {
            "status": "skipped",
            "simulated_removed_count": 0,
            "input_shape_count": None,
            "output_shape_count": None,
        },
        "impact": {
            "status": "not_applicable",
            "overall_decision": "not_applicable",
            "changed_pixel_ratio": None,
            "mean_abs_diff": None,
            "local_changed_pixel_ratio": None,
        },
        "outputs": base["outputs"],
        "warnings": warnings + [reason],
    }


def _result_base(candidate, change, outputs):
    metadata = (change or {}).get("metadata") or {}
    return {
        "change_id": candidate.get("change_id"),
        "shape_index": (change or candidate).get("shape_index"),
        "shape_uid": (change or candidate).get("shape_uid"),
        "candidate_type": metadata.get("candidate_type") or candidate.get("candidate_type"),
        "risk_level": (change or candidate).get("risk_level"),
        "trial_score": candidate.get("trial_score"),
        "outputs": outputs,
    }


def _candidate_outputs(candidate_dir):
    return {
        "candidate_feedback": str(candidate_dir / "candidate_feedback_single.json"),
        "sandbox_geometry": str(candidate_dir / "sandbox_removed_geometry.json"),
        "before_preview": str(candidate_dir / "before_preview.png"),
        "after_preview": str(candidate_dir / "after_preview.png"),
        "diff": str(candidate_dir / "diff.png"),
        "removal_report": str(candidate_dir / "removal_simulation_report.json"),
        "impact_report": str(candidate_dir / "removal_impact_report.json"),
    }


def _impact_summary(impact):
    global_metrics = impact.get("global_metrics") or {}
    local_metrics = impact.get("local_metrics") or {}
    return {
        "status": impact.get("status"),
        "overall_decision": impact.get("overall_decision"),
        "changed_pixel_ratio": global_metrics.get("changed_pixel_ratio"),
        "mean_abs_diff": global_metrics.get("mean_abs_diff"),
        "local_changed_pixel_ratio": local_metrics.get("changed_local_pixel_ratio"),
    }


def _summary(results):
    groups = {decision: [] for decision in VALID_DECISIONS}
    for result in results:
        decision = result.get("impact", {}).get("overall_decision") or "failed"
        groups.setdefault(decision, []).append(result.get("change_id"))
    ranked = sorted(
        results,
        key=lambda item: _ratio(item.get("impact", {}).get("changed_pixel_ratio")),
    )
    return {
        "safe_to_remove": groups.get("safe_to_remove", []),
        "probably_safe": groups.get("probably_safe", []),
        "risky": groups.get("risky", []),
        "failed": groups.get("failed", []),
        "not_applicable": groups.get("not_applicable", []),
        "best_candidates": [item.get("change_id") for item in ranked[:5]],
        "worst_candidates": [item.get("change_id") for item in list(reversed(ranked))[:5]],
    }


def _batch_reference(trial_report):
    if not isinstance(trial_report, dict):
        return {
            "batch_decision": None,
            "batch_changed_pixel_ratio": None,
            "batch_candidate_count": None,
        }
    return {
        "batch_decision": (trial_report.get("impact_summary") or {}).get("overall_decision"),
        "batch_changed_pixel_ratio": (trial_report.get("impact_summary") or {}).get("global_changed_pixel_ratio"),
        "batch_candidate_count": len(trial_report.get("selected_trial_candidates", [])),
    }


def _plan_by_id(plan):
    return {
        change.get("change_id"): change
        for change in plan.get("changes", [])
        if change.get("action") == "mark_candidate" and change.get("change_id")
    }


def _feedback_by_id(feedback):
    return {item.get("change_id"): item for item in feedback.get("items", []) if item.get("change_id")}


def _dedupe_candidates(candidates):
    seen = set()
    ordered = []
    for candidate in candidates or []:
        change_id = candidate.get("change_id")
        if not change_id or change_id in seen:
            continue
        seen.add(change_id)
        ordered.append(candidate)
    return ordered


def _refresh_counts(feedback):
    counts = {status: 0 for status in ("accepted", "protected", "rejected", "unsure")}
    for item in feedback.get("items", []):
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    feedback["total_feedback_items"] = len(feedback.get("items", []))
    feedback["counts_by_status"] = counts


def _write_json(data, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _impact_options(options):
    out = {"local_padding": int(options.get("local_padding", 8))}
    mapping = {
        "safe_threshold": "safe_threshold",
        "probably_safe_threshold": "probably_safe_threshold",
        "risky_threshold": "risky_threshold",
    }
    for source, target in mapping.items():
        if options.get(source) is not None:
            out[target] = float(options[source])
    return out


def _image_size(path):
    if not path:
        return None, None
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _safe_name(value):
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value))


def _path_string(path):
    return str(path) if path else None


def _ratio(value):
    if value is None:
        return 999.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 999.0
