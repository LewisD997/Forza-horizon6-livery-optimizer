from collections import Counter, defaultdict

from engine.optimizer.change_plan import make_change_entry, make_optimization_plan


TYPE_RECTANGLE = 1
TYPE_ROTATED_RECTANGLE = 2
TYPE_ROTATED_ELLIPSE = 16
TYPE_TRIANGLE = 32
TYPE_GRAD_DISK = 0xE2
TYPE_GRAD_GLOW = 0xE4

SOFT_TYPES = {TYPE_ROTATED_ELLIPSE, TYPE_GRAD_DISK, TYPE_GRAD_GLOW}


def generate_cleanup_candidate_plan(
    geometry: dict,
    analysis_report: dict | None = None,
    options: dict | None = None,
) -> dict:
    options = options or {}
    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else []
    max_candidates = int(options.get("max_candidates", 100))
    min_score = float(options.get("min_candidate_score", 0.35))
    include_low_confidence = bool(options.get("include_low_confidence", False))
    allowed_types = set(options.get("allowed_candidate_types") or [])
    input_path = options.get("input_geometry_path", "")
    output_path = options.get("output_geometry_path")

    context = _build_context(shapes, analysis_report or {})
    scored = []
    for index, shape in enumerate(shapes):
        if index == 0:
            continue
        candidate = _score_shape(index, shape, context)
        if not candidate:
            continue
        if allowed_types and candidate["candidate_type"] not in allowed_types:
            continue
        if candidate["candidate_score"] < min_score and not include_low_confidence:
            continue
        scored.append(candidate)

    scored.sort(key=lambda item: item["candidate_score"], reverse=True)
    selected = scored[:max_candidates]
    changes = [_candidate_to_change(i + 1, candidate) for i, candidate in enumerate(selected)]
    plan = make_optimization_plan(
        input_geometry_path=input_path,
        output_geometry_path=output_path,
        optimization_mode="candidate_plan",
        shape_count_before=len(shapes),
        changes=changes,
        warnings=[],
        safety_level="non_destructive",
    )
    plan["candidate_summary"] = _candidate_summary(selected, max_candidates, min_score)
    return plan


def _build_context(shapes, report):
    canvas_width, canvas_height = _canvas_size(shapes, report)
    canvas_area = max(1.0, canvas_width * canvas_height)
    bboxes = [_bbox(shape) for shape in shapes]
    areas = [_area(bbox) for bbox in bboxes]
    cells = defaultdict(list)
    ellipse_cells = defaultdict(list)
    duplicates = defaultdict(list)
    for index, shape in enumerate(shapes):
        bbox = bboxes[index]
        cell = _cell_for_bbox(bbox)
        cells[cell].append(index)
        if _shape_type(shape) == TYPE_ROTATED_ELLIPSE:
            ellipse_cells[cell].append(index)
        duplicates[_signature(shape)].append(index)
    high_diff_regions = (report.get("visual_diff") or {}).get("high_difference_regions") or []
    background_color = _color(shapes[0]) if shapes else None
    return {
        "canvas_area": canvas_area,
        "bboxes": bboxes,
        "areas": areas,
        "cells": cells,
        "ellipse_cells": ellipse_cells,
        "duplicates": duplicates,
        "high_diff_regions": high_diff_regions,
        "background_color": background_color,
    }


def _score_shape(index, shape, context):
    shape_type = _shape_type(shape)
    bbox = context["bboxes"][index]
    area = context["areas"][index]
    area_ratio = area / context["canvas_area"]
    alpha = _alpha(shape)
    cell = _cell_for_bbox(bbox)
    reasons = []
    score_by_type = {}

    if shape_type in SOFT_TYPES and alpha < 0.65 and area_ratio >= 0.002:
        reasons.append("low_alpha_soft_shape_with_visible_area")
        score_by_type["low_alpha_large_soft_shape"] = min(0.95, 0.35 + area_ratio * 18 + (0.65 - alpha))

    if area_ratio <= 0.00008 and len(context["cells"][cell]) >= 6 and index > 8:
        reasons.append("very_small_shape_inside_dense_local_cluster")
        score_by_type["tiny_fragment_cluster_member"] = min(0.85, 0.35 + len(context["cells"][cell]) / 30)

    if shape_type == TYPE_ROTATED_ELLIPSE and len(context["ellipse_cells"][cell]) >= 5 and area_ratio <= 0.004:
        reasons.append("small_ellipse_inside_local_ellipse_cluster")
        score_by_type["ellipse_cluster_member"] = min(0.85, 0.4 + len(context["ellipse_cells"][cell]) / 25)

    diff_score = _overlapping_diff_score(bbox, context["high_diff_regions"])
    if diff_score is not None and area_ratio <= 0.01:
        reasons.append("shape_overlaps_high_visual_difference_region")
        score_by_type["high_diff_overlap_member"] = min(0.9, 0.35 + diff_score * 0.65)

    if context["background_color"] and _near_color(_color(shape), context["background_color"]) and alpha >= 0.75 and area_ratio <= 0.015:
        reasons.append("shape_color_is_near_background_color")
        score_by_type["background_or_near_background_shape"] = min(0.75, 0.35 + (0.015 - area_ratio) * 12)

    duplicate_group = context["duplicates"].get(_signature(shape), [])
    if len(duplicate_group) > 1 and duplicate_group[0] != index:
        reasons.append("shape_has_duplicate_like_signature")
        score_by_type["duplicate_like_shape"] = 0.8

    if not score_by_type:
        return None
    candidate_type, score = max(score_by_type.items(), key=lambda item: item[1])
    if index < 6 and area_ratio > 0.01:
        score *= 0.5
        reasons.append("early_large_shape_downweighted_as_possible_base_layer")
    risk = "low" if score >= 0.7 and len(reasons) >= 2 and area_ratio <= 0.01 else "review_only"
    return {
        "shape_index": index,
        "shape": shape,
        "candidate_type": candidate_type,
        "candidate_score": round(score, 4),
        "region": _region_dict(bbox),
        "visual_diff_score": diff_score,
        "layer_alpha": alpha,
        "layer_area_estimate": round(area, 4),
        "primitive_type": shape_type,
        "artifact_reasons": reasons,
        "risk_level": risk,
    }


def _candidate_to_change(sequence, candidate):
    metadata = {
        "candidate_type": candidate["candidate_type"],
        "candidate_score": candidate["candidate_score"],
        "region": candidate["region"],
        "visual_diff_score": candidate["visual_diff_score"],
        "layer_alpha": candidate["layer_alpha"],
        "layer_area_estimate": candidate["layer_area_estimate"],
        "primitive_type": candidate["primitive_type"],
        "artifact_reasons": candidate["artifact_reasons"],
        "recommendation": "review_before_cleanup",
        "human_review_required": True,
    }
    return make_change_entry(
        change_id=f"C{sequence:04d}",
        action="mark_candidate",
        shape_index=candidate["shape_index"],
        shape=candidate["shape"],
        reason="Non-destructive cleanup candidate for future human review.",
        risk_level=candidate["risk_level"],
        status="proposed",
        before=candidate["shape"],
        after=candidate["shape"],
        rollback={"action": "none", "reason": "mark_candidate does not modify geometry"},
        metadata=metadata,
    )


def _candidate_summary(candidates, max_candidates, min_score):
    by_type = Counter(candidate["candidate_type"] for candidate in candidates)
    by_risk = Counter(candidate["risk_level"] for candidate in candidates)
    top = []
    for candidate in candidates[:10]:
        top.append(
            {
                "shape_index": candidate["shape_index"],
                "candidate_type": candidate["candidate_type"],
                "candidate_score": candidate["candidate_score"],
                "risk_level": candidate["risk_level"],
                "artifact_reasons": candidate["artifact_reasons"],
                "region": candidate["region"],
            }
        )
    return {
        "total_candidates": len(candidates),
        "candidate_counts_by_type": dict(sorted(by_type.items())),
        "candidate_counts_by_risk": dict(sorted(by_risk.items())),
        "top_candidates": top,
        "warnings": [],
        "non_destructive": True,
        "max_candidates": max_candidates,
        "min_candidate_score": min_score,
    }


def _canvas_size(shapes, report):
    image_info = report.get("image_info") or {}
    size = image_info.get("size") or {}
    if size.get("width") and size.get("height"):
        return float(size["width"]), float(size["height"])
    if shapes:
        data = shapes[0].get("data") if isinstance(shapes[0], dict) else None
        if isinstance(data, list) and len(data) >= 4:
            return abs(_number(data[2])), abs(_number(data[3]))
    return 1000.0, 1000.0


def _bbox(shape):
    data = shape.get("data") if isinstance(shape, dict) else None
    if not isinstance(data, list):
        return (0.0, 0.0, 0.0, 0.0)
    shape_type = _shape_type(shape)
    if shape_type in {TYPE_ROTATED_RECTANGLE, TYPE_ROTATED_ELLIPSE, TYPE_GRAD_DISK, TYPE_GRAD_GLOW} and len(data) >= 4:
        cx, cy = _number(data[0]), _number(data[1])
        half_w, half_h = abs(_number(data[2])), abs(_number(data[3]))
        return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
    if shape_type == TYPE_TRIANGLE and len(data) >= 6:
        xs = [_number(data[0]), _number(data[2]), _number(data[4])]
        ys = [_number(data[1]), _number(data[3]), _number(data[5])]
        return (min(xs), min(ys), max(xs), max(ys))
    if len(data) >= 4:
        x, y = _number(data[0]), _number(data[1])
        w, h = _number(data[2]), _number(data[3])
        return (min(x, x + w), min(y, y + h), max(x, x + w), max(y, y + h))
    return (0.0, 0.0, 0.0, 0.0)


def _shape_type(shape):
    try:
        return int(shape.get("type"))
    except (TypeError, ValueError, AttributeError):
        return 0


def _alpha(shape):
    color = shape.get("color") if isinstance(shape, dict) else None
    if isinstance(color, list) and len(color) >= 4:
        return max(0.0, min(1.0, _number(color[3]) / 255.0))
    return 1.0


def _color(shape):
    color = shape.get("color") if isinstance(shape, dict) else None
    if not isinstance(color, list):
        return None
    channels = [int(max(0, min(255, _number(color[i] if len(color) > i else 0)))) for i in range(3)]
    return tuple(channels)


def _near_color(a, b, threshold=18):
    if a is None or b is None:
        return False
    return sum(abs(a[i] - b[i]) for i in range(3)) <= threshold


def _area(bbox):
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _cell_for_bbox(bbox, grid=64):
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    return (int(cx // grid), int(cy // grid))


def _overlapping_diff_score(bbox, regions):
    best = None
    for region in regions:
        other = (
            _number(region.get("x")),
            _number(region.get("y")),
            _number(region.get("x")) + _number(region.get("width")),
            _number(region.get("y")) + _number(region.get("height")),
        )
        if _intersects(bbox, other):
            score = _number(region.get("difference_score"))
            best = score if best is None else max(best, score)
    return best


def _intersects(a, b):
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def _region_dict(bbox):
    return {
        "x": bbox[0],
        "y": bbox[1],
        "width": max(0.0, bbox[2] - bbox[0]),
        "height": max(0.0, bbox[3] - bbox[1]),
    }


def _signature(shape):
    return (
        _shape_type(shape),
        tuple(round(_number(value), 3) for value in shape.get("data", []) if isinstance(shape.get("data"), list)),
        tuple(int(_number(value)) for value in shape.get("color", []) if isinstance(shape.get("color"), list)),
    )


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
