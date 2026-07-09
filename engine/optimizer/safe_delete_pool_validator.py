import copy
import json
from pathlib import Path

from engine.optimizer.change_plan import make_shape_uid
from engine.optimizer.removal_impact_scorer import score_removal_impact
from engine.output.removal_impact_writer import write_removal_impact_report
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview
from engine.vision.visual_diff import compare_images


SAFE_DELETE_VALIDATION_VERSION = "0.6.12"
VALID_STATUSES = {
    "completed",
    "completed_with_warnings",
    "no_safe_delete_candidates",
    "failed",
}
BLOCKED_ACTIONS = {
    "deletion_candidate_review",
    "replacement_candidate",
    "protect_candidate",
    "unclear_needs_review",
}


def validate_safe_delete_pool(
    geometry: dict,
    visible_contribution_report: dict,
    options: dict | None = None,
) -> dict:
    options = options or {}
    original_geometry = copy.deepcopy(geometry)
    feedback = options.get("feedback") or {}
    original_feedback = copy.deepcopy(feedback)
    output_dir = Path(options.get("output_dir", "safe_delete_validation"))
    output_dir.mkdir(parents=True, exist_ok=True)
    overwrite = bool(options.get("overwrite", False))
    warnings = []

    outputs = _outputs(output_dir)
    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else []
    selected, skipped = _select_safe_delete_candidates(
        shapes,
        visible_contribution_report,
        feedback,
        warnings,
    )
    sandbox_geometry = _remove_shapes(geometry, selected)

    if selected and bool(options.get("write_sandbox_geometry", True)):
        _write_json(sandbox_geometry, outputs["sandbox_geometry"], overwrite)

    impact = _not_applicable_impact(len(shapes), len(sandbox_geometry.get("shapes", [])), len(selected))
    if selected and not bool(options.get("no_render", False)):
        try:
            _render_outputs(geometry, sandbox_geometry, outputs, options, overwrite)
            compare_images(outputs["before_preview"], outputs["after_preview"], outputs["diff"])
            removal_report = _removal_report(len(shapes), sandbox_geometry, selected)
            impact = score_removal_impact(
                outputs["before_preview"],
                outputs["after_preview"],
                removal_report=removal_report,
                options=_impact_options(options),
            )
            impact["input_paths"]["removal_simulation_report"] = None
            write_removal_impact_report(impact, outputs["impact_report"], overwrite=overwrite)
            _write_evidence_sheet(selected, outputs, impact, options, overwrite)
        except Exception as exc:
            warnings.append(f"Render or impact scoring failed: {exc}")
            impact = _failed_impact(len(shapes), len(sandbox_geometry.get("shapes", [])), len(selected), str(exc))
    elif selected and bool(options.get("no_render", False)):
        warnings.append("Rendering disabled by --no-render; impact scoring was not run.")

    status = _status(selected, skipped, warnings)
    report = _report(
        status,
        options,
        output_dir,
        len(shapes),
        sandbox_geometry,
        selected,
        skipped,
        impact,
        outputs,
        geometry != original_geometry,
        feedback != original_feedback,
        warnings,
    )
    proposal = _cleanup_proposal(
        status,
        options,
        selected,
        skipped,
        impact,
    )

    _write_json(proposal, outputs["cleanup_proposal"], overwrite)
    _write_json(report, outputs["validation_report"], overwrite)
    _write_summary(report, outputs["summary"], overwrite)
    return report


def _select_safe_delete_candidates(shapes, visible_report, feedback, warnings):
    protect_ids = set(((visible_report.get("summary") or {}).get("protect_candidate")) or [])
    feedback_by_id = _feedback_by_id(feedback)
    selected = []
    skipped = []
    used_indexes = set()
    used_ids = set()

    for result in visible_report.get("results", []) if isinstance(visible_report, dict) else []:
        change_id = result.get("change_id") or f"shape_{result.get('shape_index')}"
        shape_index = result.get("shape_index")
        reason = _skip_reason(result, shapes, protect_ids, feedback_by_id, used_indexes, used_ids)
        if reason:
            skipped.append(_skip(result, reason))
            if reason in {"shape_uid_mismatch", "shape_index_out_of_range"}:
                warnings.append(f"Safe delete candidate {change_id} skipped: {reason}.")
            continue

        used_indexes.add(shape_index)
        used_ids.add(change_id)
        shape = copy.deepcopy(shapes[shape_index])
        global_metrics = result.get("global_metrics") or {}
        local_metrics = result.get("local_metrics") or {}
        selected.append(
            {
                "change_id": change_id,
                "shape_index": shape_index,
                "shape_uid": result.get("shape_uid"),
                "candidate_type": result.get("candidate_type"),
                "contribution_class": result.get("contribution_class"),
                "recommended_action": result.get("recommended_action"),
                "global_changed_pixel_ratio": _number(global_metrics.get("global_changed_pixel_ratio")),
                "local_changed_pixel_ratio": _nullable_number(local_metrics.get("local_changed_pixel_ratio")),
                "suspected_occluded": bool(result.get("suspected_occluded")),
                "feedback_status": _feedback_status(feedback_by_id, change_id) or result.get("feedback_status"),
                "region": copy.deepcopy(result.get("region")),
                "shape": shape,
            }
        )
    return selected, skipped


def _skip_reason(result, shapes, protect_ids, feedback_by_id, used_indexes, used_ids):
    change_id = result.get("change_id") or f"shape_{result.get('shape_index')}"
    shape_index = result.get("shape_index")
    if result.get("recommended_action") != "safe_delete_pool":
        return "not_safe_delete_pool"
    if result.get("contribution_class") != "zero_or_negligible_contribution":
        return "not_zero_or_negligible_contribution"
    if result.get("removed_shape_count") != 1:
        return "removed_shape_count_not_one"
    if change_id in protect_ids:
        return "listed_as_protect_candidate"
    feedback_status = _feedback_status(feedback_by_id, change_id)
    if feedback_status in {"protected", "rejected"}:
        return f"feedback_{feedback_status}"
    if not isinstance(shape_index, int) or shape_index < 0 or shape_index >= len(shapes):
        return "shape_index_out_of_range"
    if shape_index in used_indexes:
        return "duplicate_shape_index"
    if change_id in used_ids:
        return "duplicate_change_id"
    expected_uid = make_shape_uid(shapes[shape_index], shape_index)
    if result.get("shape_uid") != expected_uid:
        return "shape_uid_mismatch"
    return None


def _remove_shapes(geometry, selected):
    sandbox = copy.deepcopy(geometry)
    shapes = sandbox.get("shapes", []) if isinstance(sandbox, dict) else []
    for index in sorted((item["shape_index"] for item in selected), reverse=True):
        del shapes[index]
    return sandbox


def _render_outputs(geometry, sandbox_geometry, outputs, options, overwrite):
    geometry_path = options.get("geometry_path")
    if not geometry_path:
        geometry_path = Path(outputs["before_geometry"])
        _write_json(geometry, geometry_path, overwrite)
    sandbox_path = outputs["sandbox_geometry"]
    if not Path(sandbox_path).exists():
        _write_json(sandbox_geometry, sandbox_path, overwrite)
    width, height = _image_size(options.get("source_image_path"))
    render_paint_studio_preview(
        str(geometry_path),
        outputs["before_preview"],
        width=width,
        height=height,
        ssaa=int(options.get("ssaa", 2)),
        export_mode="full_canvas_opaque",
    )
    render_paint_studio_preview(
        outputs["sandbox_geometry"],
        outputs["after_preview"],
        width=width,
        height=height,
        ssaa=int(options.get("ssaa", 2)),
        export_mode="full_canvas_opaque",
    )


def _cleanup_proposal(status, options, selected, skipped, impact):
    proposed = []
    for item in selected:
        proposed.append(
            {
                "change_id": item["change_id"],
                "shape_index": item["shape_index"],
                "shape_uid": item["shape_uid"],
                "reason": "zero_or_negligible_visible_contribution",
                "evidence": {
                    "global_changed_pixel_ratio": item["global_changed_pixel_ratio"],
                    "local_changed_pixel_ratio": item["local_changed_pixel_ratio"],
                    "suspected_occluded": item["suspected_occluded"],
                },
                "risk_level": "low",
                "requires_final_apply": True,
            }
        )
    proposal_status = "empty" if not selected else "proposed"
    if status == "failed":
        proposal_status = "blocked"
    return {
        "cleanup_proposal_version": SAFE_DELETE_VALIDATION_VERSION,
        "proposal_type": "safe_delete_pool",
        "status": proposal_status,
        "source_visible_contribution_report": _path_string(options.get("visible_report_path")),
        "candidate_count": len(selected),
        "proposed_removals": proposed,
        "blocked_removals": skipped,
        "impact_summary": _impact_summary(impact),
        "approval_required": True,
        "official_geometry_written": False,
    }


def _report(
    status,
    options,
    output_dir,
    input_shape_count,
    sandbox_geometry,
    selected,
    skipped,
    impact,
    outputs,
    original_geometry_modified,
    original_feedback_modified,
    warnings,
):
    output_shape_count = len(sandbox_geometry.get("shapes", []))
    return {
        "safe_delete_validation_version": SAFE_DELETE_VALIDATION_VERSION,
        "status": status,
        "input_paths": {
            "geometry": _path_string(options.get("geometry_path")),
            "visible_contribution_report": _path_string(options.get("visible_report_path")),
            "feedback": _path_string(options.get("feedback_path")),
        },
        "output_dir": str(output_dir),
        "input_shape_count": input_shape_count,
        "safe_delete_candidate_count": len(selected),
        "simulated_removed_count": len(selected),
        "output_shape_count": output_shape_count,
        "removed_shapes": [_removed_public(item) for item in selected],
        "skipped_candidates": skipped,
        "impact_summary": _impact_summary(impact),
        "outputs": {
            "sandbox_geometry": outputs["sandbox_geometry"] if selected else None,
            "before_preview": outputs["before_preview"] if selected else None,
            "after_preview": outputs["after_preview"] if selected else None,
            "diff": outputs["diff"] if selected else None,
            "impact_report": outputs["impact_report"] if selected and Path(outputs["impact_report"]).exists() else None,
            "cleanup_proposal": outputs["cleanup_proposal"],
            "summary": outputs["summary"],
            "evidence_sheet": outputs["evidence_sheet"] if selected and Path(outputs["evidence_sheet"]).exists() else None,
        },
        "safety": {
            "original_geometry_modified": original_geometry_modified,
            "original_feedback_modified": original_feedback_modified,
            "official_cleanup_output_written": False,
            "sandbox_only": True,
            "proposal_only": True,
        },
        "warnings": warnings,
    }


def _removed_public(item):
    return {
        "change_id": item["change_id"],
        "shape_index": item["shape_index"],
        "shape_uid": item["shape_uid"],
        "candidate_type": item["candidate_type"],
        "contribution_class": item["contribution_class"],
        "recommended_action": item["recommended_action"],
        "global_changed_pixel_ratio": item["global_changed_pixel_ratio"],
        "local_changed_pixel_ratio": item["local_changed_pixel_ratio"],
    }


def _removal_report(input_shape_count, sandbox_geometry, selected):
    return {
        "input_shape_count": input_shape_count,
        "output_shape_count": len(sandbox_geometry.get("shapes", [])),
        "simulated_removed_count": len(selected),
        "removed_shapes": copy.deepcopy(selected),
    }


def _impact_summary(impact):
    global_metrics = (impact or {}).get("global_metrics") or {}
    return {
        "status": (impact or {}).get("status", "not_applicable"),
        "overall_decision": (impact or {}).get("overall_decision", "not_applicable"),
        "global_changed_pixel_ratio": global_metrics.get("changed_pixel_ratio"),
        "mean_abs_diff": global_metrics.get("mean_abs_diff"),
    }


def _not_applicable_impact(input_count, output_count, removed_count):
    return {
        "status": "not_applicable_no_removals" if removed_count == 0 else "not_applicable_no_render",
        "overall_decision": "not_applicable",
        "shape_counts": {
            "input_shape_count": input_count,
            "output_shape_count": output_count,
            "simulated_removed_count": removed_count,
        },
        "global_metrics": {"changed_pixel_ratio": None, "mean_abs_diff": None},
        "warnings": [],
    }


def _failed_impact(input_count, output_count, removed_count, warning):
    return {
        "status": "failed",
        "overall_decision": "failed",
        "shape_counts": {
            "input_shape_count": input_count,
            "output_shape_count": output_count,
            "simulated_removed_count": removed_count,
        },
        "global_metrics": {"changed_pixel_ratio": None, "mean_abs_diff": None},
        "warnings": [warning],
    }


def _write_evidence_sheet(selected, outputs, impact, options, overwrite):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return

    before = Image.open(outputs["before_preview"]).convert("RGBA")
    after = Image.open(outputs["after_preview"]).convert("RGBA")
    diff = Image.open(outputs["diff"]).convert("RGBA")
    thumb_size = (260, 180)
    before_thumb = _fit(before, thumb_size, Image)
    after_thumb = _fit(after, thumb_size, Image)
    diff_thumb = _fit(diff, thumb_size, Image)
    row_height = 130
    width = 900
    height = 260 + row_height * max(1, len(selected))
    sheet = Image.new("RGBA", (width, height), (248, 248, 248, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    lines = [
        "FLO Safe Delete Pool Batch Validation",
        "Proposal only. No official cleanup geometry written.",
        f"removed: {len(selected)}    decision: {(impact or {}).get('overall_decision', 'not_applicable')}",
        f"global_changed: {((impact or {}).get('global_metrics') or {}).get('changed_pixel_ratio')}",
        f"mean_abs_diff: {((impact or {}).get('global_metrics') or {}).get('mean_abs_diff')}",
    ]
    y = 12
    for line in lines:
        draw.text((12, y), line, fill=(20, 20, 20, 255), font=font)
        y += 18
    for label, image, x in (
        ("before", before_thumb, 12),
        ("after", after_thumb, 312),
        ("diff", diff_thumb, 612),
    ):
        draw.text((x, 112), label, fill=(0, 0, 0, 255), font=font)
        sheet.alpha_composite(image, (x, 132))
    y = 330
    for item in selected:
        region = item.get("region")
        before_crop = _crop_region(before, region, int(options.get("local_padding", 8)), Image)
        after_crop = _crop_region(after, region, int(options.get("local_padding", 8)), Image)
        diff_crop = _crop_region(diff, region, int(options.get("local_padding", 8)), Image)
        draw.text(
            (12, y),
            f"{item['change_id']} shape={item['shape_index']} type={item.get('candidate_type')} "
            f"global={item.get('global_changed_pixel_ratio')} local={item.get('local_changed_pixel_ratio')}",
            fill=(20, 20, 20, 255),
            font=font,
        )
        sheet.alpha_composite(_fit(before_crop, (120, 90), Image), (12, y + 24))
        sheet.alpha_composite(_fit(after_crop, (120, 90), Image), (152, y + 24))
        sheet.alpha_composite(_fit(diff_crop, (120, 90), Image), (292, y + 24))
        y += row_height
    _save_image(sheet, outputs["evidence_sheet"], overwrite)


def _crop_region(image, region, padding, image_module):
    if not isinstance(region, dict):
        return image.copy()
    x = int(_number(region.get("x")) - padding)
    y = int(_number(region.get("y")) - padding)
    w = int(_number(region.get("width")) + padding * 2)
    h = int(_number(region.get("height")) + padding * 2)
    box = (
        max(0, x),
        max(0, y),
        min(image.width, max(0, x) + max(1, w)),
        min(image.height, max(0, y) + max(1, h)),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return image.copy()
    return image.crop(box)


def _fit(image, size, image_module):
    tile = image.copy()
    tile.thumbnail(size, image_module.Resampling.NEAREST)
    canvas = image_module.new("RGBA", size, (235, 235, 235, 255))
    canvas.alpha_composite(tile, ((size[0] - tile.width) // 2, (size[1] - tile.height) // 2))
    return canvas


def _outputs(output_dir):
    return {
        "validation_report": str(output_dir / "safe_delete_pool_validation_report.json"),
        "cleanup_proposal": str(output_dir / "safe_delete_cleanup_proposal.json"),
        "summary": str(output_dir / "safe_delete_validation_summary.txt"),
        "sandbox_geometry": str(output_dir / "sandbox_safe_deleted_geometry.json"),
        "before_geometry": str(output_dir / "sandbox_original_geometry.json"),
        "before_preview": str(output_dir / "before_preview.png"),
        "after_preview": str(output_dir / "after_preview.png"),
        "diff": str(output_dir / "diff.png"),
        "impact_report": str(output_dir / "removal_impact_report.json"),
        "evidence_sheet": str(output_dir / "evidence_sheet.png"),
    }


def _write_summary(report, path, overwrite):
    lines = [
        "FLO Safe Delete Pool Batch Validator",
        "",
        f"Status: {report['status']}",
        f"Input shapes: {report['input_shape_count']}",
        f"Safe delete candidates: {report['safe_delete_candidate_count']}",
        f"Simulated removed: {report['simulated_removed_count']}",
        f"Output shapes: {report['output_shape_count']}",
        f"Impact decision: {report['impact_summary']['overall_decision']}",
        f"Global changed pixel ratio: {report['impact_summary']['global_changed_pixel_ratio']}",
        "",
        "Removed changes:",
    ]
    for item in report["removed_shapes"]:
        lines.append(f"- {item['change_id']} shape_index={item['shape_index']}")
    lines.extend(
        [
            "",
            "Safety:",
            "- sandbox_only: true",
            "- proposal_only: true",
            "- official_cleanup_output_written: false",
        ]
    )
    _write_text(path, "\n".join(lines), overwrite)


def _status(selected, skipped, warnings):
    if not selected:
        return "no_safe_delete_candidates"
    if warnings or skipped:
        return "completed_with_warnings"
    return "completed"


def _feedback_by_id(feedback):
    out = {}
    for item in feedback.get("items", []) if isinstance(feedback, dict) else []:
        if item.get("change_id"):
            out.setdefault(item["change_id"], []).append(item)
    return out


def _feedback_status(feedback_by_id, change_id):
    items = feedback_by_id.get(change_id) or []
    statuses = [item.get("status") for item in items if item.get("status")]
    if "protected" in statuses:
        return "protected"
    if "rejected" in statuses:
        return "rejected"
    return statuses[0] if statuses else None


def _skip(result, reason):
    return {
        "change_id": result.get("change_id") or f"shape_{result.get('shape_index')}",
        "shape_index": result.get("shape_index"),
        "shape_uid": result.get("shape_uid"),
        "contribution_class": result.get("contribution_class"),
        "recommended_action": result.get("recommended_action"),
        "reason": reason,
    }


def _impact_options(options):
    return {
        "safe_threshold": options.get("safe_threshold"),
        "probably_safe_threshold": options.get("probably_safe_threshold"),
        "risky_threshold": options.get("risky_threshold"),
        "local_padding": options.get("local_padding", 8),
    }


def _image_size(path):
    if not path:
        return None, None
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def _write_json(data, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path, text, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _save_image(image, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _path_string(path):
    return str(path) if path else None


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _nullable_number(value):
    if value is None:
        return None
    return _number(value)
