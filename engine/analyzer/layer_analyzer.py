from collections import defaultdict
from math import hypot


def analyze_layers(layers, image_info):
    issues = []
    issues.extend(_duplicate_layers(layers))
    issues.extend(_very_small_layers(layers, image_info))
    issues.extend(_stretched_layers(layers))
    issues.extend(_nearly_identical_colors(layers))
    issues.extend(_edge_fixing_fragments(layers, image_info))

    messy_regions = _messy_clusters(layers)
    removable_ids = {
        issue["layer_id"]
        for issue in issues
        if issue.get("layer_id") and issue["type"] in {"duplicate_layer", "very_small_layer", "edge_fixing_fragment"}
    }

    notes = [
        "MVP only reports suspicious layers. It does not rewrite or delete the livery.",
        "The original image is used for basic visual context only in this version.",
        "Possible fully covered layers are not detected yet because occlusion analysis is not implemented.",
    ]

    if image_info.get("edge_density") is not None:
        notes.append(f"Reference image edge density: {image_info['edge_density']}")

    return {
        "issues": issues,
        "suspected_messy_regions": messy_regions,
        "estimated_removable_layers": len(removable_ids),
        "notes": notes,
    }


def score_layers(layers, analysis):
    total_layers = max(1, len(layers))
    issues = analysis["issues"]
    messy_regions = analysis["suspected_messy_regions"]

    tiny_count = _issue_count(issues, "very_small_layer")
    stretched_count = _issue_count(issues, "extremely_stretched_layer")
    duplicate_count = _issue_count(issues, "duplicate_layer")
    fragment_count = _issue_count(issues, "edge_fixing_fragment")
    removable_count = analysis["estimated_removable_layers"]
    messy_layer_count = sum(region.get("layer_count", 0) for region in messy_regions)

    cleanliness_penalty = (
        duplicate_count * 8
        + tiny_count * 4
        + stretched_count * 3
        + fragment_count * 5
        + len(messy_regions) * 6
    )
    fragmentation_raw = (
        tiny_count * 7
        + fragment_count * 8
        + messy_layer_count * 4
        + stretched_count * 2
    )
    removable_ratio = removable_count / total_layers
    efficiency_penalty = removable_ratio * 70 + duplicate_count * 5 + tiny_count * 2

    return {
        "cleanliness_score": _score_from_penalty(cleanliness_penalty),
        "fragmentation_score": _clamp_score(fragmentation_raw),
        "layer_efficiency_score": _score_from_penalty(efficiency_penalty),
    }


def _issue_count(issues, issue_type):
    return sum(1 for issue in issues if issue["type"] == issue_type)


def _score_from_penalty(penalty):
    return _clamp_score(100 - penalty)


def _clamp_score(value):
    return round(max(0, min(100, value)), 2)


def _duplicate_layers(layers):
    seen = defaultdict(list)
    for layer in layers:
        key = (
            layer["shape"],
            round(layer["x"], 3),
            round(layer["y"], 3),
            round(layer["width"], 3),
            round(layer["height"], 3),
            round(layer["rotation"], 3),
            layer["color"],
            round(layer["opacity"], 3),
        )
        seen[key].append(layer["id"])

    issues = []
    for ids in seen.values():
        if len(ids) > 1:
            for duplicate_id in ids[1:]:
                issues.append(
                    {
                        "type": "duplicate_layer",
                        "severity": "high",
                        "layer_id": duplicate_id,
                        "message": f"Layer appears to duplicate {ids[0]}.",
                        "related_layers": ids,
                    }
                )
    return issues


def _very_small_layers(layers, image_info):
    width, height = _image_size(image_info)
    image_area = max(1.0, width * height)
    issues = []

    for layer in layers:
        area = abs(layer["width"] * layer["height"])
        if area <= 16 or area / image_area < 0.00008:
            issues.append(
                {
                    "type": "very_small_layer",
                    "severity": "medium",
                    "layer_id": layer["id"],
                    "message": "Layer is tiny and may be visual noise or a micro patch.",
                    "area": round(area, 4),
                }
            )
    return issues


def _stretched_layers(layers):
    issues = []
    for layer in layers:
        width = abs(layer["width"])
        height = abs(layer["height"])
        if width == 0 or height == 0:
            continue
        ratio = max(width / height, height / width)
        if ratio >= 12:
            issues.append(
                {
                    "type": "extremely_stretched_layer",
                    "severity": "medium",
                    "layer_id": layer["id"],
                    "message": "Layer is extremely stretched and may be a crude edge or line workaround.",
                    "aspect_ratio": round(ratio, 3),
                }
            )
    return issues


def _nearly_identical_colors(layers):
    issues = []
    checked = set()
    for index, layer in enumerate(layers):
        color_a = _hex_to_rgb(layer["color"])
        if color_a is None:
            continue
        for other in layers[index + 1 :]:
            pair_key = tuple(sorted((layer["id"], other["id"])))
            if pair_key in checked:
                continue
            checked.add(pair_key)
            color_b = _hex_to_rgb(other["color"])
            if color_b is None:
                continue
            if _color_distance(color_a, color_b) <= 6 and layer["color"] != other["color"]:
                issues.append(
                    {
                        "type": "nearly_identical_colors",
                        "severity": "low",
                        "layer_id": layer["id"],
                        "message": "Layer color is nearly identical to another layer color.",
                        "related_layers": [layer["id"], other["id"]],
                        "colors": [layer["color"], other["color"]],
                    }
                )
                break
    return issues


def _edge_fixing_fragments(layers, image_info):
    width, height = _image_size(image_info)
    margin_x = max(4, width * 0.03)
    margin_y = max(4, height * 0.03)
    issues = []

    for layer in layers:
        layer_area = abs(layer["width"] * layer["height"])
        near_edge = (
            layer["x"] <= margin_x
            or layer["y"] <= margin_y
            or layer["x"] + layer["width"] >= width - margin_x
            or layer["y"] + layer["height"] >= height - margin_y
        )
        thin = min(abs(layer["width"]), abs(layer["height"])) <= 3
        if near_edge and thin and layer_area <= max(400, width * height * 0.004):
            issues.append(
                {
                    "type": "edge_fixing_fragment",
                    "severity": "medium",
                    "layer_id": layer["id"],
                    "message": "Small thin layer near an image edge looks like an edge-fixing fragment.",
                }
            )
    return issues


def _messy_clusters(layers):
    small_layers = [
        layer
        for layer in layers
        if abs(layer["width"] * layer["height"]) <= 80
    ]
    clusters = []
    used = set()

    for layer in small_layers:
        if layer["id"] in used:
            continue
        cluster = [layer]
        center = _center(layer)
        for other in small_layers:
            if other["id"] == layer["id"]:
                continue
            if hypot(center[0] - _center(other)[0], center[1] - _center(other)[1]) <= 24:
                cluster.append(other)

        if len(cluster) >= 5:
            for member in cluster:
                used.add(member["id"])
            xs = [member["x"] for member in cluster]
            ys = [member["y"] for member in cluster]
            clusters.append(
                {
                    "type": "messy_small_layer_cluster",
                    "severity": "medium",
                    "layer_count": len(cluster),
                    "layer_ids": [member["id"] for member in cluster],
                    "bounds": {
                        "x": min(xs),
                        "y": min(ys),
                        "width": max(xs) - min(xs),
                        "height": max(ys) - min(ys),
                    },
                    "message": "Many small layers are packed into a small area. This may be replaceable with cleaner primitives.",
                }
            )

    return clusters


def _center(layer):
    return (layer["x"] + layer["width"] / 2, layer["y"] + layer["height"] / 2)


def _image_size(image_info):
    size = image_info.get("size") or {}
    return float(size.get("width") or 1000), float(size.get("height") or 1000)


def _hex_to_rgb(value):
    if not isinstance(value, str) or not value.startswith("#") or len(value) != 7:
        return None
    try:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError:
        return None


def _color_distance(color_a, color_b):
    return hypot(color_a[0] - color_b[0], color_a[1] - color_b[1], color_a[2] - color_b[2])
