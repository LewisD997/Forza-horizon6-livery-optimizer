from pathlib import Path


IMPACT_VERSION = "0.6.7"

DEFAULT_THRESHOLDS = {
    "safe_changed_pixel_ratio": 0.002,
    "probably_safe_changed_pixel_ratio": 0.01,
    "risky_changed_pixel_ratio": 0.03,
}


def score_removal_impact(
    before_image_path: str,
    after_image_path: str,
    removal_report: dict | None = None,
    plan: dict | None = None,
    feedback: dict | None = None,
    options: dict | None = None,
) -> dict:
    options = options or {}
    thresholds = _thresholds(options)
    warnings = []
    recommendations = [
        "Use this score only for sandbox review.",
        "Do not treat this report as final cleanup approval.",
    ]
    shape_counts = _shape_counts(removal_report)
    removed_count = shape_counts["simulated_removed_count"]

    base = {
        "impact_version": IMPACT_VERSION,
        "status": "failed",
        "overall_decision": "failed",
        "input_paths": {
            "before_preview": str(before_image_path) if before_image_path else None,
            "after_preview": str(after_image_path) if after_image_path else None,
            "removal_simulation_report": None,
        },
        "shape_counts": shape_counts,
        "global_metrics": _empty_global_metrics(),
        "local_metrics": _empty_local_metrics(),
        "per_removed_shape_metrics": [],
        "thresholds": thresholds,
        "warnings": warnings,
        "recommendations": recommendations,
    }

    if removed_count <= 0:
        base["status"] = "not_applicable_no_removals"
        base["overall_decision"] = "not_applicable"
        base["recommendations"].append("No accepted candidates were removed, so impact scoring is not applicable.")
        return base

    before_path = Path(before_image_path) if before_image_path else None
    after_path = Path(after_image_path) if after_image_path else None
    if not before_path or not before_path.exists() or not after_path or not after_path.exists():
        base["status"] = "missing_inputs"
        base["overall_decision"] = "failed"
        warnings.append("before_preview or after_preview is missing.")
        return base

    try:
        arrays = _load_image_arrays(before_path, after_path)
        if arrays["before_size"] != arrays["after_size"]:
            base["status"] = "failed"
            base["overall_decision"] = "failed"
            warnings.append(
                f"Image size mismatch: before={arrays['before_size']} after={arrays['after_size']}."
            )
            return base
        global_metrics = _compute_global_metrics(arrays)
        per_shape = _per_removed_shape_metrics(
            arrays,
            removal_report or {},
            plan or {},
            feedback or {},
            thresholds,
            int(options.get("local_padding", 8)),
        )
        local_metrics = _aggregate_local_metrics(per_shape)
        decision = _overall_decision(global_metrics, local_metrics, thresholds)
        base.update(
            {
                "status": "completed",
                "overall_decision": decision,
                "global_metrics": global_metrics,
                "local_metrics": local_metrics,
                "per_removed_shape_metrics": per_shape,
            }
        )
        if decision == "risky":
            recommendations.append("Review removed candidates manually before any future cleanup proposal.")
        elif decision in {"safe_to_remove", "probably_safe"}:
            recommendations.append("Impact looks small, but future cleanup still requires explicit approval.")
        return base
    except Exception as exc:
        base["status"] = "failed"
        base["overall_decision"] = "failed"
        warnings.append(f"Impact scoring failed: {exc}")
        return base


def _thresholds(options):
    thresholds = dict(DEFAULT_THRESHOLDS)
    if options.get("safe_threshold") is not None:
        thresholds["safe_changed_pixel_ratio"] = float(options["safe_threshold"])
    if options.get("probably_safe_threshold") is not None:
        thresholds["probably_safe_changed_pixel_ratio"] = float(options["probably_safe_threshold"])
    if options.get("risky_threshold") is not None:
        thresholds["risky_changed_pixel_ratio"] = float(options["risky_threshold"])
    return thresholds


def _shape_counts(removal_report):
    report = removal_report or {}
    return {
        "input_shape_count": int(report.get("input_shape_count") or 0),
        "output_shape_count": int(report.get("output_shape_count") or 0),
        "simulated_removed_count": int(report.get("simulated_removed_count") or 0),
    }


def _empty_global_metrics():
    return {
        "mean_abs_diff": None,
        "max_abs_diff": None,
        "changed_pixel_count": None,
        "changed_pixel_ratio": None,
        "alpha_changed_pixel_ratio": None,
        "rgb_changed_pixel_ratio": None,
        "changed_bbox": None,
    }


def _empty_local_metrics():
    return {
        "mean_local_diff": None,
        "max_local_diff": None,
        "changed_local_pixel_ratio": None,
    }


def _load_image_arrays(before_path, after_path):
    from PIL import Image
    import numpy as np

    before = Image.open(before_path).convert("RGBA")
    after = Image.open(after_path).convert("RGBA")
    return {
        "before": np.asarray(before, dtype=np.int16),
        "after": np.asarray(after, dtype=np.int16),
        "before_size": before.size,
        "after_size": after.size,
        "np": np,
    }


def _compute_global_metrics(arrays, epsilon=2):
    np = arrays["np"]
    before = arrays["before"]
    after = arrays["after"]
    diff = np.abs(after - before)
    rgb_diff = diff[:, :, :3]
    alpha_diff = diff[:, :, 3]
    rgb_changed = np.any(rgb_diff > epsilon, axis=2)
    alpha_changed = alpha_diff > epsilon
    changed = rgb_changed | alpha_changed
    pixel_count = max(1, changed.size)
    bbox = _changed_bbox(changed, np)
    return {
        "mean_abs_diff": round(float(rgb_diff.mean() / 255.0), 6),
        "max_abs_diff": round(float(rgb_diff.max() / 255.0), 6),
        "changed_pixel_count": int(changed.sum()),
        "changed_pixel_ratio": round(float(changed.sum() / pixel_count), 6),
        "alpha_changed_pixel_ratio": round(float(alpha_changed.sum() / pixel_count), 6),
        "rgb_changed_pixel_ratio": round(float(rgb_changed.sum() / pixel_count), 6),
        "changed_bbox": bbox,
    }


def _changed_bbox(mask, np):
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    left = int(xs.min())
    top = int(ys.min())
    right = int(xs.max()) + 1
    bottom = int(ys.max()) + 1
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
        "right": right,
        "bottom": bottom,
    }


def _per_removed_shape_metrics(arrays, removal_report, plan, feedback, thresholds, padding):
    plan_by_id = {change.get("change_id"): change for change in plan.get("changes", []) if change.get("change_id")}
    feedback_by_id = {item.get("change_id"): item for item in feedback.get("items", []) if item.get("change_id")}
    metrics = []
    for removed in removal_report.get("removed_shapes", []):
        change_id = removed.get("change_id")
        change = plan_by_id.get(change_id, {})
        item = feedback_by_id.get(change_id, {})
        metadata = change.get("metadata") or {}
        region = metadata.get("region") or removed.get("region") or _shape_region(removed.get("shape"))
        local = _local_diff(arrays, region, padding)
        metrics.append(
            {
                "change_id": change_id,
                "shape_index": removed.get("shape_index"),
                "shape_uid": removed.get("shape_uid"),
                "candidate_type": removed.get("candidate_type") or metadata.get("candidate_type"),
                "risk_level": change.get("risk_level"),
                "feedback_status": removed.get("feedback_status") or item.get("status"),
                "region": local["region"],
                "local_mean_abs_diff": local["mean_abs_diff"],
                "local_changed_pixel_ratio": local["changed_pixel_ratio"],
                "local_max_abs_diff": local["max_abs_diff"],
                "local_decision": _local_decision(local["changed_pixel_ratio"], thresholds),
            }
        )
    return metrics


def _local_diff(arrays, region, padding, epsilon=2):
    np = arrays["np"]
    before = arrays["before"]
    after = arrays["after"]
    height, width = before.shape[:2]
    box = _region_to_box(region, width, height, padding)
    if box is None:
        return {"region": None, "mean_abs_diff": None, "max_abs_diff": None, "changed_pixel_ratio": None}
    x0, y0, x1, y1 = box
    diff = np.abs(after[y0:y1, x0:x1, :] - before[y0:y1, x0:x1, :])
    rgb_diff = diff[:, :, :3]
    changed = np.any(diff > epsilon, axis=2)
    pixel_count = max(1, changed.size)
    return {
        "region": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0, "right": x1, "bottom": y1},
        "mean_abs_diff": round(float(rgb_diff.mean() / 255.0), 6),
        "max_abs_diff": round(float(rgb_diff.max() / 255.0), 6),
        "changed_pixel_ratio": round(float(changed.sum() / pixel_count), 6),
    }


def _region_to_box(region, width, height, padding):
    if not isinstance(region, dict):
        return None
    x = _number(region.get("x"))
    y = _number(region.get("y"))
    w = _number(region.get("width"))
    h = _number(region.get("height"))
    if w <= 0 or h <= 0:
        return None
    x0 = max(0, int(x - padding))
    y0 = max(0, int(y - padding))
    x1 = min(width, int(x + w + padding + 0.999))
    y1 = min(height, int(y + h + padding + 0.999))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _shape_region(shape):
    if not isinstance(shape, dict):
        return None
    data = shape.get("data") if isinstance(shape.get("data"), list) else []
    shape_type = shape.get("type")
    if shape_type in {2, 16, 0xE2, 0xE4} and len(data) >= 4:
        cx, cy, rx, ry = (_number(data[0]), _number(data[1]), abs(_number(data[2])), abs(_number(data[3])))
        return {"x": cx - rx, "y": cy - ry, "width": rx * 2, "height": ry * 2}
    if shape_type == 32 and len(data) >= 6:
        xs = [_number(data[0]), _number(data[2]), _number(data[4])]
        ys = [_number(data[1]), _number(data[3]), _number(data[5])]
        return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
    if len(data) >= 4:
        x, y, w, h = _number(data[0]), _number(data[1]), _number(data[2]), _number(data[3])
        return {"x": min(x, x + w), "y": min(y, y + h), "width": abs(w), "height": abs(h)}
    return None


def _aggregate_local_metrics(per_shape):
    numeric = [item for item in per_shape if item.get("local_changed_pixel_ratio") is not None]
    if not numeric:
        return _empty_local_metrics()
    return {
        "mean_local_diff": round(sum(item["local_mean_abs_diff"] for item in numeric) / len(numeric), 6),
        "max_local_diff": round(max(item["local_max_abs_diff"] for item in numeric), 6),
        "changed_local_pixel_ratio": round(max(item["local_changed_pixel_ratio"] for item in numeric), 6),
    }


def _overall_decision(global_metrics, local_metrics, thresholds):
    global_ratio = global_metrics.get("changed_pixel_ratio") or 0.0
    local_ratio = local_metrics.get("changed_local_pixel_ratio")
    local_ratio = 0.0 if local_ratio is None else local_ratio
    if global_ratio <= thresholds["safe_changed_pixel_ratio"] and local_ratio <= thresholds["probably_safe_changed_pixel_ratio"]:
        return "safe_to_remove"
    if global_ratio <= thresholds["probably_safe_changed_pixel_ratio"] and local_ratio <= thresholds["risky_changed_pixel_ratio"]:
        return "probably_safe"
    return "risky"


def _local_decision(ratio, thresholds):
    if ratio is None:
        return "not_available"
    if ratio <= thresholds["safe_changed_pixel_ratio"]:
        return "safe_to_remove"
    if ratio <= thresholds["probably_safe_changed_pixel_ratio"]:
        return "probably_safe"
    return "risky"


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
