ROUND_PRIMITIVES = {"ellipse", "circle", "rotated_ellipse", "glow", "disk"}
GLOW_DISK_PRIMITIVES = {"glow", "disk"}
LINE_WARNING_PRIMITIVES = {"line", "line_internal_only"}


def analyze_anime_artifacts(layers, image_info=None, visual_diff=None, grid_size=64) -> dict:
    width, height = _image_size(image_info)
    grid_size = max(8, int(grid_size or 64))
    diff_regions = _visual_diff_regions(visual_diff)
    regions = []

    for y in range(0, int(height), grid_size):
        for x in range(0, int(width), grid_size):
            cell = {
                "x": float(x),
                "y": float(y),
                "width": float(min(grid_size, width - x)),
                "height": float(min(grid_size, height - y)),
            }
            cell_layers = [layer for layer in layers if _overlaps_layer(cell, layer)]
            if not cell_layers:
                continue

            region = _analyze_region(cell, cell_layers, diff_regions)
            if region["artifact_score"] > 0:
                regions.append(region)

    regions.sort(key=lambda region: region["artifact_score"], reverse=True)
    for index, region in enumerate(regions, start=1):
        region["region_id"] = f"A{index:03d}"

    summary = _summary(regions, layers)
    notes = [
        "Anime artifact analysis is diagnostic-only and does not modify input layers.",
        "Scores are heuristic signals for visible generated artifacts, not proof of incorrect geometry.",
        "mask_or_unknown is preserved as neutral unless other local signals make the region suspicious.",
    ]

    return {
        "summary": summary,
        "regions": regions,
        "notes": notes,
    }


def _analyze_region(cell, layers, diff_regions):
    round_count = sum(1 for layer in layers if _shape(layer) in ROUND_PRIMITIVES)
    ellipse_count = sum(1 for layer in layers if _shape(layer) in {"ellipse", "rotated_ellipse"})
    circle_count = sum(1 for layer in layers if _shape(layer) == "circle")
    tiny_count = sum(1 for layer in layers if _area(layer) <= 64)
    glow_disk_count = sum(1 for layer in layers if _shape(layer) in GLOW_DISK_PRIMITIVES)
    line_count = sum(1 for layer in layers if _shape(layer) in LINE_WARNING_PRIMITIVES)
    visual_diff_score = _max_overlapping_diff_score(cell, diff_regions)

    suspected_artifacts = []
    score = 0.0

    if round_count >= 3:
        score += 18 + (round_count - 3) * 5
        suspected_artifacts.append("round_primitive_cluster")
    elif round_count >= 2:
        score += 8
        suspected_artifacts.append("visible_round_primitives")

    if ellipse_count >= 2 and _has_small_ellipse_cluster(layers):
        score += 16 + (ellipse_count - 2) * 4
        suspected_artifacts.append("small_ellipse_cluster")

    if tiny_count >= 5:
        score += 20 + (tiny_count - 5) * 3
        suspected_artifacts.append("fragmentation_risk")
    elif tiny_count >= 3:
        score += 10
        suspected_artifacts.append("tiny_layer_group")

    if glow_disk_count and tiny_count >= 2:
        score += 15 + glow_disk_count * 4
        suspected_artifacts.append("soft_blur_risk")
    elif glow_disk_count >= 2:
        score += 10
        suspected_artifacts.append("glow_disk_blob_risk")

    if line_count:
        score += line_count * 8
        suspected_artifacts.append("line_internal_only_warning")

    if visual_diff_score is not None:
        score += min(30.0, visual_diff_score * 60)
        if visual_diff_score >= 0.18:
            suspected_artifacts.append("high_visual_difference_overlap")

    score = round(min(100.0, score), 2)

    return {
        "region_id": "",
        "x": cell["x"],
        "y": cell["y"],
        "width": cell["width"],
        "height": cell["height"],
        "priority": _priority(score),
        "artifact_score": score,
        "round_primitive_count": round_count,
        "ellipse_count": ellipse_count,
        "circle_count": circle_count,
        "tiny_layer_count": tiny_count,
        "glow_disk_count": glow_disk_count,
        "line_internal_only_count": line_count,
        "visual_diff_score": visual_diff_score,
        "suspected_artifacts": sorted(set(suspected_artifacts)),
        "reason": _reason(suspected_artifacts, score),
    }


def _summary(regions, layers):
    visible_round_count = sum(1 for layer in layers if _shape(layer) in ROUND_PRIMITIVES)
    high_priority_count = sum(1 for region in regions if region["priority"] == "high")
    ellipse_cluster_count = sum(1 for region in regions if "small_ellipse_cluster" in region["suspected_artifacts"])
    soft_blur_count = sum(
        1
        for region in regions
        if "soft_blur_risk" in region["suspected_artifacts"]
        or "glow_disk_blob_risk" in region["suspected_artifacts"]
    )
    fragmentation_count = sum(
        1
        for region in regions
        if "fragmentation_risk" in region["suspected_artifacts"]
        or "tiny_layer_group" in region["suspected_artifacts"]
    )
    line_count = sum(1 for layer in layers if _shape(layer) in LINE_WARNING_PRIMITIVES)
    overall_score = 0.0
    if regions:
        top_regions = regions[:5]
        overall_score = sum(region["artifact_score"] for region in top_regions) / len(top_regions)

    return {
        "artifact_region_count": len(regions),
        "high_priority_region_count": high_priority_count,
        "visible_round_primitive_count": visible_round_count,
        "ellipse_cluster_count": ellipse_cluster_count,
        "soft_blur_risk_count": soft_blur_count,
        "fragmentation_risk_count": fragmentation_count,
        "line_internal_only_count": line_count,
        "overall_anime_artifact_score": round(overall_score, 2),
    }


def _visual_diff_regions(visual_diff):
    if not isinstance(visual_diff, dict):
        return []
    regions = visual_diff.get("high_difference_regions")
    if not isinstance(regions, list):
        return []
    return [region for region in regions if isinstance(region, dict)]


def _max_overlapping_diff_score(cell, diff_regions):
    scores = [
        _number(region.get("difference_score"))
        for region in diff_regions
        if _boxes_overlap(cell, region)
    ]
    if not scores:
        return None
    return round(max(scores), 4)


def _has_small_ellipse_cluster(layers):
    ellipses = [layer for layer in layers if _shape(layer) in {"ellipse", "rotated_ellipse"}]
    return sum(1 for layer in ellipses if _area(layer) <= 1024) >= 2


def _overlaps_layer(cell, layer):
    layer_box = _layer_box(layer)
    return _boxes_overlap(cell, layer_box)


def _boxes_overlap(a, b):
    ax1 = _number(a.get("x"))
    ay1 = _number(a.get("y"))
    ax2 = ax1 + _number(a.get("width"))
    ay2 = ay1 + _number(a.get("height"))
    bx1 = _number(b.get("x"))
    by1 = _number(b.get("y"))
    bx2 = bx1 + _number(b.get("width"))
    by2 = by1 + _number(b.get("height"))

    left_a, right_a = sorted((ax1, ax2))
    top_a, bottom_a = sorted((ay1, ay2))
    left_b, right_b = sorted((bx1, bx2))
    top_b, bottom_b = sorted((by1, by2))

    return left_a < right_b and right_a > left_b and top_a < bottom_b and bottom_a > top_b


def _layer_box(layer):
    return {
        "x": _number(layer.get("x")),
        "y": _number(layer.get("y")),
        "width": _number(layer.get("width")),
        "height": _number(layer.get("height")),
    }


def _area(layer):
    return abs(_number(layer.get("width")) * _number(layer.get("height")))


def _shape(layer):
    return str(layer.get("shape", "")).lower()


def _priority(score):
    if score >= 55:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _reason(suspected_artifacts, score):
    if not suspected_artifacts:
        return "No strong anime artifact signal was found."
    return f"Heuristic artifact score {round(score, 2)} from: {', '.join(sorted(set(suspected_artifacts)))}."


def _image_size(image_info):
    size = (image_info or {}).get("size") or {}
    return float(size.get("width") or 1000), float(size.get("height") or 1000)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
