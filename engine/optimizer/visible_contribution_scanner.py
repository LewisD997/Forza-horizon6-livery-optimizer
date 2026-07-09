import copy
import csv
import json
from pathlib import Path

from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview
from engine.vision.visual_diff import compare_images


VISIBLE_CONTRIBUTION_VERSION = "0.6.11"

CONTRIBUTION_CLASSES = {
    "zero_or_negligible_contribution",
    "barely_visible_contribution",
    "visible_minor_contribution",
    "important_visible_contribution",
    "critical_contribution",
    "scan_failed",
}

RECOMMENDED_ACTIONS = {
    "safe_delete_pool",
    "deletion_candidate_review",
    "replacement_candidate",
    "protect_candidate",
    "unclear_needs_review",
}

DEFAULT_THRESHOLDS = {
    "zero_global": 0.00005,
    "zero_local": 0.005,
    "barely_global": 0.00020,
    "barely_local": 0.020,
    "minor_global": 0.00100,
    "minor_local": 0.080,
    "important_global": 0.00300,
    "important_local": 0.250,
}


def scan_visible_contribution(
    geometry: dict,
    plan: dict | None = None,
    feedback: dict | None = None,
    options: dict | None = None,
) -> dict:
    options = options or {}
    plan = plan or {}
    feedback = feedback or {}
    original_geometry = copy.deepcopy(geometry)
    original_feedback = copy.deepcopy(feedback)
    output_dir = Path(options.get("output_dir", "visible_contribution"))
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    thresholds = _thresholds(options)
    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else []
    selected = _select_shapes(shapes, plan, feedback, options)

    baseline_path = output_dir / "baseline_preview.png"
    baseline_rendered = False
    try:
        if selected:
            _render_geometry(options.get("geometry_path"), baseline_path, options)
            baseline_rendered = True
    except Exception as exc:
        warnings.append(f"Baseline render failed: {exc}")

    results = []
    cards = []
    for item in selected:
        result = _scan_one_shape(
            geometry,
            item,
            baseline_path,
            baseline_rendered,
            thresholds,
            output_dir,
            options,
        )
        results.append(result)
        warnings.extend(result.get("warnings", []))
        card = (result.get("outputs") or {}).get("evidence_card")
        if card:
            cards.append(card)

    if cards:
        try:
            _write_evidence_sheet(cards, output_dir / "evidence_sheet.png", options.get("overwrite", False))
        except Exception as exc:
            warnings.append(f"Evidence sheet failed: {exc}")

    report = {
        "visible_contribution_version": VISIBLE_CONTRIBUTION_VERSION,
        "status": _status(selected, results, warnings),
        "scan_scope": options.get("scope", "candidate_plan"),
        "input_paths": {
            "geometry": _path_string(options.get("geometry_path")),
            "plan": _path_string(options.get("plan_path")),
            "feedback": _path_string(options.get("feedback_path")),
        },
        "shape_count": len(shapes),
        "scanned_shape_count": len(results),
        "results": results,
        "summary": _summary(results),
        "thresholds": thresholds,
        "safety": {
            "original_geometry_modified": geometry != original_geometry,
            "original_feedback_modified": feedback != original_feedback,
            "official_cleanup_output_written": False,
            "sandbox_only": True,
        },
        "warnings": warnings,
    }
    _write_json(report, output_dir / "visible_contribution_report.json", options.get("overwrite", False))
    _write_summary_text(report, output_dir / "visible_contribution_summary.txt", options.get("overwrite", False))
    _write_csv(report, output_dir / "visible_contribution_table.csv", options.get("overwrite", False))
    return report


def _scan_one_shape(geometry, item, baseline_path, baseline_rendered, thresholds, output_dir, options):
    shape_index = item["shape_index"]
    label = _result_id(item)
    shape_dir = output_dir / "shapes" / _safe_name(label)
    shape_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "after_preview": str(shape_dir / "after_preview.png"),
        "diff": str(shape_dir / "diff.png"),
        "diff_crop": str(shape_dir / "diff_crop.png"),
        "amplified_diff_crop": str(shape_dir / "amplified_diff_crop.png"),
        "evidence_card": str(shape_dir / "evidence_card.png"),
        "metadata": str(shape_dir / "contribution_metadata.json"),
    }
    warnings = []
    if not baseline_rendered:
        return _failed_result(item, outputs, ["baseline_render_missing"])
    try:
        sandbox = copy.deepcopy(geometry)
        del sandbox["shapes"][shape_index]
        sandbox_path = shape_dir / "sandbox_removed_geometry.json"
        _write_json(sandbox, sandbox_path, options.get("overwrite", False))
        _render_geometry(sandbox_path, outputs["after_preview"], options)
        compare_images(str(baseline_path), outputs["after_preview"], outputs["diff"])
        metrics = _compute_metrics(
            baseline_path,
            outputs["after_preview"],
            item.get("region"),
            int(options.get("local_padding", 8)),
        )
        contribution_class = _classify(metrics["global_metrics"], metrics["local_metrics"], thresholds)
        action = _recommended_action(item, contribution_class)
        score = _score(metrics["global_metrics"], metrics["local_metrics"])
        suspected_occluded = contribution_class in {
            "zero_or_negligible_contribution",
            "barely_visible_contribution",
        }
        _write_evidence(
            baseline_path,
            outputs["after_preview"],
            outputs["diff"],
            outputs,
            item,
            metrics,
            contribution_class,
            action,
            options,
        )
        result = {
            **_result_base(item),
            "global_metrics": metrics["global_metrics"],
            "local_metrics": metrics["local_metrics"],
            "visible_contribution_score": score,
            "contribution_class": contribution_class,
            "recommended_action": action,
            "suspected_occluded": suspected_occluded,
            "removed_shape_count": 1,
            "outputs": outputs,
            "warnings": warnings,
        }
        _write_json(
            {
                "result": result,
                "crop_box": metrics.get("crop_box"),
                "thresholds": thresholds,
            },
            outputs["metadata"],
            options.get("overwrite", False),
        )
        return result
    except Exception as exc:
        return _failed_result(item, outputs, [f"scan_failed: {exc}"])


def _select_shapes(shapes, plan, feedback, options):
    scope = options.get("scope", "candidate_plan")
    max_scan = int(options.get("max_scan_shapes", 30))
    feedback_by_id = {item.get("change_id"): item for item in feedback.get("items", []) if item.get("change_id")}
    candidates = []

    if scope == "explicit":
        candidates.extend(_explicit_candidates(shapes, plan, options))
    elif scope == "layer_range":
        start = max(0, int(options.get("start_index", 0)))
        end = min(len(shapes) - 1, int(options.get("end_index", len(shapes) - 1)))
        candidates.extend(_shape_item(index, shapes[index], None, None) for index in range(start, end + 1))
    else:
        changes = [
            change
            for change in plan.get("changes", [])
            if change.get("action") == "mark_candidate"
            and isinstance(change.get("shape_index"), int)
            and 0 <= change["shape_index"] < len(shapes)
        ]
        if scope == "low_risk_candidate":
            changes = [change for change in changes if change.get("risk_level") == "low"]
        for change in changes:
            item = _shape_item(change["shape_index"], shapes[change["shape_index"]], change, feedback_by_id.get(change.get("change_id")))
            candidates.append(item)
        if scope == "feedback_filtered":
            candidates = [item for item in candidates if _feedback_allowed(item.get("feedback_status"), options)]

    if scope in {"candidate_plan", "low_risk_candidate"}:
        candidates = [item for item in candidates if _feedback_allowed(item.get("feedback_status"), options)]
        candidates.sort(key=_candidate_sort_key)

    return _dedupe(candidates)[: max(0, max_scan)]


def _explicit_candidates(shapes, plan, options):
    changes_by_id = {change.get("change_id"): change for change in plan.get("changes", []) if change.get("change_id")}
    out = []
    for change_id in _split(options.get("change_ids")):
        change = changes_by_id.get(change_id)
        if change and isinstance(change.get("shape_index"), int) and 0 <= change["shape_index"] < len(shapes):
            out.append(_shape_item(change["shape_index"], shapes[change["shape_index"]], change, None))
    for index in _int_list(options.get("shape_indexes")):
        if 0 <= index < len(shapes):
            out.append(_shape_item(index, shapes[index], None, None))
    return out


def _shape_item(index, shape, change, feedback_item):
    metadata = (change or {}).get("metadata") or {}
    return {
        "change_id": (change or {}).get("change_id"),
        "shape_index": index,
        "shape_uid": (change or {}).get("shape_uid"),
        "shape_type": shape.get("type") if isinstance(shape, dict) else None,
        "candidate_type": metadata.get("candidate_type"),
        "risk_level": (change or {}).get("risk_level"),
        "feedback_status": (feedback_item or {}).get("status"),
        "region": metadata.get("region") or _shape_region(shape),
        "layer_alpha": metadata.get("layer_alpha") or _alpha(shape),
        "layer_area_estimate": metadata.get("layer_area_estimate") or _area(_shape_region(shape)),
    }


def _feedback_allowed(status, options):
    if status == "protected" and bool(options.get("exclude_protected", True)):
        return False
    if status == "rejected" and bool(options.get("exclude_rejected", True)):
        return False
    if status == "unsure" and not bool(options.get("include_unsure", True)):
        return False
    if status == "accepted" and not bool(options.get("include_accepted", True)):
        return False
    return True


def _render_geometry(geometry_path, output_path, options):
    if not geometry_path:
        raise ValueError("geometry_path is required for Paint Studio source rendering.")
    width, height = _image_size(options.get("source_image_path"))
    render_paint_studio_preview(
        str(geometry_path),
        str(output_path),
        width=width,
        height=height,
        ssaa=int(options.get("ssaa", 2)),
        export_mode="full_canvas_opaque",
    )


def _compute_metrics(before_path, after_path, region, padding):
    from PIL import Image
    import numpy as np

    before = Image.open(before_path).convert("RGBA")
    after = Image.open(after_path).convert("RGBA")
    before_arr = np.asarray(before, dtype=np.int16)
    after_arr = np.asarray(after, dtype=np.int16)
    diff = np.abs(after_arr - before_arr)
    rgb = diff[:, :, :3]
    alpha = diff[:, :, 3]
    changed = np.any(diff > 2, axis=2)
    rgb_changed = np.any(rgb > 2, axis=2)
    alpha_changed = alpha > 2
    pixel_count = max(1, changed.size)
    bbox = _changed_bbox(changed, np)
    global_metrics = {
        "global_mean_abs_diff": round(float(rgb.mean() / 255.0), 6),
        "global_max_abs_diff": round(float(rgb.max() / 255.0), 6),
        "global_changed_pixel_count": int(changed.sum()),
        "global_changed_pixel_ratio": round(float(changed.sum() / pixel_count), 6),
        "global_alpha_changed_pixel_ratio": round(float(alpha_changed.sum() / pixel_count), 6),
        "global_rgb_changed_pixel_ratio": round(float(rgb_changed.sum() / pixel_count), 6),
        "global_changed_bbox": bbox,
    }
    local_box = _local_box(region, bbox, before.size, padding)
    local_metrics = _local_metrics(before_arr, after_arr, local_box, padding, np)
    contribution_area_ratio = round(float((bbox or {}).get("width", 0) * (bbox or {}).get("height", 0) / pixel_count), 6)
    global_metrics["contribution_area_ratio"] = contribution_area_ratio
    return {
        "global_metrics": global_metrics,
        "local_metrics": local_metrics,
        "crop_box": _box_dict(_crop_box(before.size, region, bbox, padding)),
    }


def _local_metrics(before, after, box, padding, np):
    if not box:
        return {
            "local_mean_abs_diff": None,
            "local_max_abs_diff": None,
            "local_changed_pixel_ratio": None,
            "local_changed_pixel_count": None,
            "local_bbox": None,
            "local_padding": padding,
        }
    x0, y0, x1, y1 = box
    diff = np.abs(after[y0:y1, x0:x1, :] - before[y0:y1, x0:x1, :])
    rgb = diff[:, :, :3]
    changed = np.any(diff > 2, axis=2)
    count = max(1, changed.size)
    return {
        "local_mean_abs_diff": round(float(rgb.mean() / 255.0), 6),
        "local_max_abs_diff": round(float(rgb.max() / 255.0), 6),
        "local_changed_pixel_ratio": round(float(changed.sum() / count), 6),
        "local_changed_pixel_count": int(changed.sum()),
        "local_bbox": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0, "right": x1, "bottom": y1},
        "local_padding": padding,
    }


def _classify(global_metrics, local_metrics, thresholds):
    g = global_metrics.get("global_changed_pixel_ratio") or 0.0
    l = local_metrics.get("local_changed_pixel_ratio")
    l = 0.0 if l is None else l
    if g <= thresholds["zero_global"] and l <= thresholds["zero_local"]:
        return "zero_or_negligible_contribution"
    if g <= thresholds["barely_global"] and l <= thresholds["barely_local"]:
        return "barely_visible_contribution"
    if g <= thresholds["minor_global"] and l <= thresholds["minor_local"]:
        return "visible_minor_contribution"
    if g > thresholds["important_global"] or l > thresholds["important_local"]:
        return "critical_contribution"
    return "important_visible_contribution"


def _recommended_action(item, contribution_class):
    if contribution_class == "scan_failed":
        return "unclear_needs_review"
    if item.get("feedback_status") in {"protected", "rejected"}:
        return "protect_candidate"
    if item.get("shape_index", 999) < 5 and contribution_class != "zero_or_negligible_contribution":
        return "protect_candidate"
    candidate_type = item.get("candidate_type")
    if contribution_class == "zero_or_negligible_contribution":
        return "safe_delete_pool"
    if contribution_class == "barely_visible_contribution":
        return "safe_delete_pool" if candidate_type == "tiny_fragment_cluster_member" else "deletion_candidate_review"
    if contribution_class == "visible_minor_contribution":
        return "replacement_candidate" if candidate_type == "low_alpha_large_soft_shape" else "deletion_candidate_review"
    if contribution_class == "important_visible_contribution":
        return "replacement_candidate"
    if contribution_class == "critical_contribution":
        return "protect_candidate"
    return "unclear_needs_review"


def _write_evidence(before_path, after_path, diff_path, outputs, item, metrics, contribution_class, action, options):
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont

    before = Image.open(before_path).convert("RGBA")
    after = Image.open(after_path).convert("RGBA")
    diff = Image.open(diff_path).convert("RGBA")
    padding = int(options.get("crop_padding", 32))
    scale = max(1, int(options.get("upscale", 4)))
    amplify = float(options.get("amplify_diff", 6.0))
    crop = _crop_box(before.size, item.get("region"), metrics["global_metrics"].get("global_changed_bbox"), padding)
    before_crop = _crop_upscale(before, crop, scale, Image)
    after_crop = _crop_upscale(after, crop, scale, Image)
    diff_crop = _crop_upscale(diff, crop, scale, Image)
    amplified = ImageEnhance.Contrast(diff_crop).enhance(amplify).point(lambda value: min(255, int(value * amplify)))
    box = _local_scaled(item.get("region"), crop, scale)
    changed = _local_scaled(metrics["global_metrics"].get("global_changed_bbox"), crop, scale)
    for image in (before_crop, after_crop, diff_crop, amplified):
        _draw_boxes(image, box, changed, ImageDraw)
    card = _card(item, before_crop, after_crop, amplified, metrics, contribution_class, action, Image, ImageDraw, ImageFont)
    _save(diff_crop, outputs["diff_crop"], options.get("overwrite", False))
    _save(amplified, outputs["amplified_diff_crop"], options.get("overwrite", False))
    _save(card, outputs["evidence_card"], options.get("overwrite", False))


def _card(item, before_crop, after_crop, amplified, metrics, contribution_class, action, Image, ImageDraw, ImageFont):
    font = ImageFont.load_default()
    width = max(980, before_crop.width + after_crop.width + amplified.width + 80)
    height = max(before_crop.height, after_crop.height, amplified.height) + 190
    card = Image.new("RGBA", (width, height), (248, 248, 248, 255))
    draw = ImageDraw.Draw(card)
    g = metrics["global_metrics"]
    l = metrics["local_metrics"]
    lines = [
        f"shape_index: {item.get('shape_index')}    change_id: {item.get('change_id')}",
        f"type: {item.get('candidate_type')}    risk: {item.get('risk_level')}    feedback: {item.get('feedback_status')}",
        f"class: {contribution_class}    action: {action}    suspected_occluded: {contribution_class in {'zero_or_negligible_contribution','barely_visible_contribution'}}",
        f"global_changed: {g.get('global_changed_pixel_ratio')}    local_changed: {l.get('local_changed_pixel_ratio')}",
        f"mean: {g.get('global_mean_abs_diff')}    max: {g.get('global_max_abs_diff')}",
    ]
    y = 10
    for line in lines:
        draw.text((12, y), line, fill=(20, 20, 20, 255), font=font)
        y += 18
    x = 12
    for label, tile in (("before", before_crop), ("after", after_crop), ("amplified diff", amplified)):
        draw.text((x, 120), label, fill=(0, 0, 0, 255), font=font)
        card.alpha_composite(tile, (x, 140))
        x += tile.width + 24
    return card


def _write_evidence_sheet(cards, path, overwrite):
    from PIL import Image

    images = [Image.open(card).convert("RGBA") for card in cards if Path(card).exists()]
    if not images:
        return
    width = max(image.width for image in images)
    height = sum(image.height for image in images) + 12 * (len(images) + 1)
    sheet = Image.new("RGBA", (width, height), (238, 238, 238, 255))
    y = 12
    for image in images:
        sheet.alpha_composite(image, (0, y))
        y += image.height + 12
    _save(sheet, path, overwrite)


def _summary(results):
    summary = {key: [] for key in CONTRIBUTION_CLASSES | RECOMMENDED_ACTIONS}
    for result in results:
        ident = result.get("change_id") or f"shape_{result.get('shape_index')}"
        summary.setdefault(result.get("contribution_class"), []).append(ident)
        summary.setdefault(result.get("recommended_action"), []).append(ident)
    return summary


def _status(selected, results, warnings):
    if not selected:
        return "no_shapes_to_scan"
    if warnings or any(result.get("contribution_class") == "scan_failed" for result in results):
        return "completed_with_warnings"
    return "completed"


def _failed_result(item, outputs, warnings):
    return {
        **_result_base(item),
        "global_metrics": {},
        "local_metrics": {},
        "visible_contribution_score": 0.0,
        "contribution_class": "scan_failed",
        "recommended_action": "unclear_needs_review",
        "suspected_occluded": False,
        "removed_shape_count": 0,
        "outputs": outputs,
        "warnings": warnings,
    }


def _result_base(item):
    return {
        "change_id": item.get("change_id"),
        "shape_index": item.get("shape_index"),
        "shape_uid": item.get("shape_uid"),
        "shape_type": item.get("shape_type"),
        "candidate_type": item.get("candidate_type"),
        "risk_level": item.get("risk_level"),
        "feedback_status": item.get("feedback_status"),
        "region": item.get("region"),
        "layer_alpha": item.get("layer_alpha"),
        "layer_area_estimate": item.get("layer_area_estimate"),
    }


def _write_summary_text(report, path, overwrite):
    lines = [
        "FLO Visible Contribution Scanner",
        "",
        f"Status: {report['status']}",
        f"Scanned shapes: {report['scanned_shape_count']}",
        "",
        "Contribution classes:",
    ]
    for key in sorted(CONTRIBUTION_CLASSES):
        lines.append(f"- {key}: {len(report['summary'].get(key, []))} {report['summary'].get(key, [])}")
    lines.append("")
    lines.append("Recommended actions:")
    for key in sorted(RECOMMENDED_ACTIONS):
        lines.append(f"- {key}: {len(report['summary'].get(key, []))} {report['summary'].get(key, [])}")
    _write_text(path, "\n".join(lines), overwrite)


def _write_csv(report, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "change_id",
                "shape_index",
                "candidate_type",
                "risk_level",
                "feedback_status",
                "contribution_class",
                "recommended_action",
                "global_changed_pixel_ratio",
                "local_changed_pixel_ratio",
                "visible_contribution_score",
            ],
        )
        writer.writeheader()
        for result in report["results"]:
            writer.writerow(
                {
                    "change_id": result.get("change_id"),
                    "shape_index": result.get("shape_index"),
                    "candidate_type": result.get("candidate_type"),
                    "risk_level": result.get("risk_level"),
                    "feedback_status": result.get("feedback_status"),
                    "contribution_class": result.get("contribution_class"),
                    "recommended_action": result.get("recommended_action"),
                    "global_changed_pixel_ratio": (result.get("global_metrics") or {}).get("global_changed_pixel_ratio"),
                    "local_changed_pixel_ratio": (result.get("local_metrics") or {}).get("local_changed_pixel_ratio"),
                    "visible_contribution_score": result.get("visible_contribution_score"),
                }
            )


def _thresholds(options):
    thresholds = dict(DEFAULT_THRESHOLDS)
    mapping = {
        "zero_threshold": "zero_global",
        "barely_threshold": "barely_global",
        "minor_threshold": "minor_global",
        "important_threshold": "important_global",
    }
    for source, target in mapping.items():
        if options.get(source) is not None:
            thresholds[target] = float(options[source])
    return thresholds


def _candidate_sort_key(item):
    return (
        0 if item.get("risk_level") == "low" else 1,
        _number(item.get("layer_area_estimate"), 999999),
        item.get("shape_index", 999999),
    )


def _dedupe(items):
    seen = set()
    out = []
    for item in items:
        index = item.get("shape_index")
        if index in seen:
            continue
        seen.add(index)
        out.append(item)
    return out


def _shape_region(shape):
    if not isinstance(shape, dict):
        return None
    data = shape.get("data") if isinstance(shape.get("data"), list) else []
    shape_type = shape.get("type")
    if shape_type in {2, 16, 0xE2, 0xE4} and len(data) >= 4:
        cx, cy, rx, ry = _number(data[0]), _number(data[1]), abs(_number(data[2])), abs(_number(data[3]))
        return {"x": cx - rx, "y": cy - ry, "width": rx * 2, "height": ry * 2}
    if shape_type == 32 and len(data) >= 6:
        xs = [_number(data[0]), _number(data[2]), _number(data[4])]
        ys = [_number(data[1]), _number(data[3]), _number(data[5])]
        return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
    if len(data) >= 4:
        x, y, w, h = _number(data[0]), _number(data[1]), _number(data[2]), _number(data[3])
        return {"x": min(x, x + w), "y": min(y, y + h), "width": abs(w), "height": abs(h)}
    return None


def _changed_bbox(mask, np):
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    return {"x": left, "y": top, "width": right - left, "height": bottom - top, "right": right, "bottom": bottom}


def _local_box(region, changed_bbox, size, padding):
    width, height = size
    source = region if isinstance(region, dict) else changed_bbox
    if not isinstance(source, dict):
        return (0, 0, width, height)
    x = _number(source.get("x"))
    y = _number(source.get("y"))
    w = _number(source.get("width"))
    h = _number(source.get("height"))
    if w <= 0 or h <= 0:
        return (0, 0, width, height)
    x0 = max(0, int(x - padding))
    y0 = max(0, int(y - padding))
    x1 = min(width, int(x + w + padding + 0.999))
    y1 = min(height, int(y + h + padding + 0.999))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else (0, 0, width, height)


def _crop_box(size, region, changed_bbox, padding):
    width, height = size
    boxes = [_dict_to_box(region), _dict_to_box(changed_bbox)]
    boxes = [box for box in boxes if box]
    if not boxes:
        return (0, 0, width, height)
    x0 = max(0, min(box[0] for box in boxes) - padding)
    y0 = max(0, min(box[1] for box in boxes) - padding)
    x1 = min(width, max(box[2] for box in boxes) + padding)
    y1 = min(height, max(box[3] for box in boxes) + padding)
    return (int(x0), int(y0), int(x1), int(y1))


def _dict_to_box(region):
    if not isinstance(region, dict):
        return None
    x, y, w, h = _number(region.get("x")), _number(region.get("y")), _number(region.get("width")), _number(region.get("height"))
    if w <= 0 or h <= 0:
        return None
    return (x, y, x + w, y + h)


def _local_scaled(region, crop, scale):
    box = _dict_to_box(region)
    if not box:
        return None
    return tuple(int((value - offset) * scale) for value, offset in zip(box, (crop[0], crop[1], crop[0], crop[1])))


def _draw_boxes(image, candidate_box, changed_box, ImageDraw):
    draw = ImageDraw.Draw(image)
    if candidate_box:
        draw.rectangle(candidate_box, outline=(0, 128, 255, 255), width=2)
        draw.text((candidate_box[0] + 4, max(0, candidate_box[1] - 14)), "candidate", fill=(0, 80, 180, 255))
    if changed_box:
        draw.rectangle(changed_box, outline=(255, 64, 0, 255), width=2)
        draw.text((changed_box[0] + 4, max(0, changed_box[1] - 28)), "changed", fill=(200, 40, 0, 255))


def _crop_upscale(image, crop, scale, Image):
    cropped = image.crop(crop)
    if scale <= 1:
        return cropped
    return cropped.resize((cropped.width * scale, cropped.height * scale), Image.Resampling.NEAREST)


def _save(image, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


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


def _alpha(shape):
    color = shape.get("color") if isinstance(shape, dict) else None
    if isinstance(color, list) and len(color) >= 4:
        return round(max(0.0, min(1.0, _number(color[3]) / 255.0)), 4)
    return None


def _area(region):
    if not isinstance(region, dict):
        return None
    return max(0.0, _number(region.get("width"))) * max(0.0, _number(region.get("height")))


def _score(global_metrics, local_metrics):
    g = global_metrics.get("global_changed_pixel_ratio") or 0.0
    l = local_metrics.get("local_changed_pixel_ratio") or 0.0
    return round(min(1.0, g * 50.0 + l), 6)


def _image_size(path):
    if not path:
        return None, None
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _split(value):
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _int_list(value):
    out = []
    for item in _split(value):
        try:
            out.append(int(item))
        except ValueError:
            pass
    return out


def _result_id(item):
    change_id = item.get("change_id")
    if change_id:
        return f"{change_id}_shape_{item.get('shape_index')}"
    return f"shape_{item.get('shape_index')}"


def _box_dict(box):
    if not box:
        return None
    x0, y0, x1, y1 = box
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0, "right": x1, "bottom": y1}


def _safe_name(value):
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value))


def _path_string(path):
    return str(path) if path else None


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
