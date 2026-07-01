from collections import Counter, defaultdict
from math import hypot

from engine.knowledge.primitive_kb import (
    classify_primitive_usage,
    get_primitive_info,
    suggest_replacements,
)


SAFE_TYPES = {"duplicate_layer", "very_small_layer", "fully_covered_layer", "opacity_near_zero"}
SMART_TYPES = {
    "extremely_stretched_layer",
    "extreme_stretch",
    "excessive_small_fragments",
    "overused_round_shapes",
    "muddy_curve",
    "possible_line_replacement",
    "possible_arc_replacement",
    "nearly_identical_colors",
}
RECONSTRUCTION_TYPES = {
    "messy_small_layer_cluster",
    "high_visual_difference_region",
    "edge_fixing_fragment",
    "fragmented_noisy_area",
}


def generate_optimization_suggestions(layers, issues, visual_diff=None, primitive_kb=None):
    layer_by_id = {layer["id"]: layer for layer in layers}
    suggestions = []

    for issue in issues:
        issue_type = issue["type"]
        if issue_type in SAFE_TYPES:
            suggestions.append(_issue_suggestion(issue, layer_by_id, "safe"))
        elif issue_type == "edge_fixing_fragment":
            suggestions.append(_issue_suggestion(issue, layer_by_id, "reconstruction"))
        elif issue_type in SMART_TYPES:
            suggestions.append(_issue_suggestion(issue, layer_by_id, "smart"))

    suggestions.extend(_opacity_near_zero_suggestions(layers))
    suggestions.extend(_overused_round_shape_suggestions(layers))
    suggestions.extend(_small_fragment_cluster_suggestions(layers))
    suggestions.extend(_high_diff_region_suggestions(layers, visual_diff))

    suggestions = [suggestion for suggestion in suggestions if suggestion is not None]
    suggestions.sort(key=_rank_key)
    return _strip_internal_fields(_assign_ids(suggestions))


def summarize_suggestions(suggestions):
    counts = Counter(suggestion["mode"] for suggestion in suggestions)
    return {
        "total_suggestions": len(suggestions),
        "safe": counts.get("safe", 0),
        "smart": counts.get("smart", 0),
        "reconstruction": counts.get("reconstruction", 0),
        "estimated_total_layer_saving": sum(
            suggestion["estimated_layer_saving"] for suggestion in suggestions
        ),
    }


def _issue_suggestion(issue, layer_by_id, mode):
    layer_ids = _issue_layer_ids(issue)
    layers = [layer_by_id[layer_id] for layer_id in layer_ids if layer_id in layer_by_id]
    if not layers:
        return None

    primary_layer = layers[0]
    problem_type = _normalize_problem_type(issue["type"])
    current_primitives = sorted({layer["shape"] for layer in layers})
    suggested_primitives = _suggested_primitives(issue, primary_layer, problem_type)

    return {
        "suggestion_id": "",
        "priority": _priority(mode, issue, layers),
        "mode": mode,
        "region": _bounds(layers),
        "problem_type": problem_type,
        "current_layers": [layer["id"] for layer in layers],
        "current_primitives": current_primitives,
        "primitive_traits": _primitive_traits(layers),
        "suggested_action": _suggested_action(problem_type, mode, suggested_primitives),
        "suggested_primitives": suggested_primitives,
        "estimated_layer_saving": _estimated_saving(problem_type, mode, layers),
        "risk": _risk(mode, problem_type),
        "reason": _reason(issue, primary_layer, problem_type, suggested_primitives),
        "primitive_reason": issue.get("primitive_reason") or _reason(
            issue, primary_layer, problem_type, suggested_primitives
        ),
    }


def _opacity_near_zero_suggestions(layers):
    suggestions = []
    for layer in layers:
        if layer.get("opacity", 1) > 0.03:
            continue
        suggested_primitives = suggest_replacements(layer["shape"], "tiny_invisible_detail")
        reason = "Layer opacity is near zero, so it is likely invisible or too weak to justify a layer slot."
        suggestions.append(
            {
                "suggestion_id": "",
                "priority": "high",
                "mode": "safe",
                "region": _bounds([layer]),
                "problem_type": "opacity_near_zero",
                "current_layers": [layer["id"]],
                "current_primitives": [layer["shape"]],
                "primitive_traits": _primitive_traits([layer]),
                "suggested_action": "Remove this near-transparent layer if visual inspection confirms it is not contributing.",
                "suggested_primitives": suggested_primitives,
                "estimated_layer_saving": 1,
                "risk": "low",
                "reason": reason,
                "primitive_reason": reason,
            }
        )
    return suggestions


def _overused_round_shape_suggestions(layers):
    round_layers = [
        layer
        for layer in layers
        if get_primitive_info(layer["shape"])["category"] in {"round_detail", "soft_curve"}
        and abs(layer["width"] * layer["height"]) <= 80
    ]
    if len(round_layers) < 5:
        return []

    return [
        {
            "suggestion_id": "",
            "priority": "medium",
            "mode": "smart",
            "region": _bounds(round_layers),
            "problem_type": "overused_round_shapes",
            "current_layers": [layer["id"] for layer in round_layers],
            "current_primitives": sorted({layer["shape"] for layer in round_layers}),
            "primitive_traits": _primitive_traits(round_layers),
            "suggested_action": "Review repeated tiny round primitives and merge them into cleaner hand-shaped patches where possible.",
            "suggested_primitives": ["polygon", "ellipse"],
            "estimated_layer_saving": max(1, len(round_layers) - 2),
            "risk": "medium",
            "reason": "Many small round shapes in one livery often read as generated noise rather than intentional hand-drawn detail.",
            "primitive_reason": "Round detail primitives are useful, but repeated tiny round patches can look noisy instead of hand drawn.",
        }
    ]


def _small_fragment_cluster_suggestions(layers):
    small_layers = [layer for layer in layers if abs(layer["width"] * layer["height"]) <= 80]
    clusters = []
    used = set()

    for layer in small_layers:
        if layer["id"] in used:
            continue
        center = _layer_center(layer)
        cluster = [
            other
            for other in small_layers
            if hypot(center[0] - _layer_center(other)[0], center[1] - _layer_center(other)[1]) <= 24
        ]
        if len(cluster) < 5:
            continue
        for member in cluster:
            used.add(member["id"])
        clusters.append(cluster)

    suggestions = []
    for cluster in clusters:
        suggestions.append(
            {
                "suggestion_id": "",
                "priority": "high" if len(cluster) >= 8 else "medium",
                "mode": "reconstruction",
                "region": _bounds(cluster),
                "problem_type": "excessive_small_fragments",
                "current_layers": [layer["id"] for layer in cluster],
                "current_primitives": sorted({layer["shape"] for layer in cluster}),
                "primitive_traits": _primitive_traits(cluster),
                "suggested_action": "Collapse this dense cluster of tiny layers into one or two cleaner hand-shaped primitives.",
                "suggested_primitives": _region_replacements(cluster),
                "estimated_layer_saving": max(1, len(cluster) - 2),
                "risk": "high",
                "reason": "A dense group of tiny generated layers usually indicates fragmented local construction that can be cleaner as a larger intentional shape.",
                "primitive_reason": "Small detail primitives are being used as fragments; a larger fill primitive can often preserve meaning with fewer layers.",
            }
        )
    return suggestions


def _high_diff_region_suggestions(layers, visual_diff):
    if not visual_diff:
        return []

    suggestions = []
    for region in visual_diff.get("high_difference_regions", []):
        nearby_layers = _layers_near_region(layers, region)
        if len(nearby_layers) < 3:
            continue
        small_count = sum(1 for layer in nearby_layers if abs(layer["width"] * layer["height"]) <= 80)
        if small_count < 2:
            continue

        suggestions.append(
            {
                "suggestion_id": "",
                "priority": "high" if region.get("difference_score", 0) >= 0.32 else "medium",
                "mode": "reconstruction",
                "region": _region(region),
                "problem_type": "high_visual_difference_region",
                "current_layers": [layer["id"] for layer in nearby_layers],
                "current_primitives": sorted({layer["shape"] for layer in nearby_layers}),
                "primitive_traits": _primitive_traits(nearby_layers),
                "suggested_action": "Locally reconstruct this high-difference region with fewer cleaner primitives instead of refitting the full image.",
                "suggested_primitives": _region_replacements(nearby_layers),
                "estimated_layer_saving": max(1, small_count - 1),
                "risk": "high",
                "reason": f"Visual diff score {region.get('difference_score')} overlaps several nearby generated layers, which suggests a local reconstruction candidate.",
                "primitive_reason": "The current primitive mix does not match the reference well in this local region.",
                "_visual_diff_score": region.get("difference_score", 0),
            }
        )
    return suggestions


def _issue_layer_ids(issue):
    ids = []
    if issue.get("layer_id"):
        ids.append(issue["layer_id"])
    ids.extend(issue.get("related_layers", []))
    return list(dict.fromkeys(ids))


def _suggested_primitives(issue, layer, problem_type):
    if issue.get("possible_replacements"):
        return issue["possible_replacements"]
    return suggest_replacements(layer["shape"], problem_type)


def _suggested_action(problem_type, mode, suggested_primitives):
    primitive_text = ", ".join(suggested_primitives) if suggested_primitives else "no replacement"
    actions = {
        "duplicate_layer": "Remove the duplicate layer if it has no intentional stacking effect.",
        "tiny_invisible_detail": "Review whether this tiny layer is visible enough to justify its cost.",
        "extreme_stretch": f"Replace the stretched primitive with a cleaner {primitive_text} primitive.",
        "near_identical_colors": "Merge near-identical color decisions where they do not change the silhouette.",
        "possible_line_replacement": "Replace edge-fixing fragments with a cleaner stroke or single edge primitive.",
        "high_visual_difference_region": "Rebuild this local region with cleaner primitive choices.",
    }
    return actions.get(problem_type, f"Review this {mode} candidate and consider {primitive_text}.")


def _estimated_saving(problem_type, mode, layers):
    if problem_type == "duplicate_layer":
        return max(1, len(layers) - 1)
    if problem_type in {"tiny_invisible_detail", "opacity_near_zero", "fully_covered_layer"}:
        return 1
    if problem_type in {"near_identical_colors", "extreme_stretch", "possible_line_replacement"}:
        return max(1, len(layers) // 2)
    if mode == "reconstruction":
        return max(1, len(layers) - 2)
    return 1


def _priority(mode, issue, layers):
    if mode == "safe" and issue.get("severity") == "high":
        return "high"
    if mode == "safe":
        return "medium"
    if mode == "reconstruction":
        return "high" if len(layers) >= 4 else "medium"
    return "medium"


def _risk(mode, problem_type):
    if mode == "safe":
        return "low"
    if mode == "smart":
        return "medium"
    return "high"


def _reason(issue, layer, problem_type, suggested_primitives):
    usage = classify_primitive_usage(layer)
    primitive = get_primitive_info(layer["shape"])
    primitive_reason = issue.get("primitive_reason")
    if primitive_reason:
        return primitive_reason
    if problem_type == "high_visual_difference_region":
        return "This region differs from the reference image and contains nearby generated fragments."
    return (
        f"{primitive['display_name']} has traits {usage['visual_traits']}; "
        f"replacement candidates are {suggested_primitives}."
    )


def _bounds(layers):
    if not layers:
        return None
    left = min(min(layer["x"], layer["x"] + layer["width"]) for layer in layers)
    top = min(min(layer["y"], layer["y"] + layer["height"]) for layer in layers)
    right = max(max(layer["x"], layer["x"] + layer["width"]) for layer in layers)
    bottom = max(max(layer["y"], layer["y"] + layer["height"]) for layer in layers)
    return {
        "x": round(left, 3),
        "y": round(top, 3),
        "width": round(right - left, 3),
        "height": round(bottom - top, 3),
    }


def _region(region):
    return {
        "x": region["x"],
        "y": region["y"],
        "width": region["width"],
        "height": region["height"],
    }


def _layers_near_region(layers, region):
    center = (region["x"] + region["width"] / 2, region["y"] + region["height"] / 2)
    radius = max(region["width"], region["height"]) * 1.5
    nearby = []
    for layer in layers:
        layer_center = (layer["x"] + layer["width"] / 2, layer["y"] + layer["height"] / 2)
        if hypot(center[0] - layer_center[0], center[1] - layer_center[1]) <= radius:
            nearby.append(layer)
    return nearby


def _layer_center(layer):
    return (layer["x"] + layer["width"] / 2, layer["y"] + layer["height"] / 2)


def _region_replacements(layers):
    replacements = []
    for layer in layers:
        replacements.extend(suggest_replacements(layer["shape"], "excessive_small_fragments"))
    if not replacements:
        return ["polygon"]
    return sorted(set(replacements))[:4]


def _primitive_traits(layers):
    traits = []
    for layer in layers:
        traits.extend(get_primitive_info(layer["shape"]).get("visual_traits", []))
    return sorted(set(traits))


def _normalize_problem_type(problem_type):
    mapping = {
        "very_small_layer": "tiny_invisible_detail",
        "extremely_stretched_layer": "extreme_stretch",
        "nearly_identical_colors": "near_identical_colors",
        "edge_fixing_fragment": "possible_line_replacement",
    }
    return mapping.get(problem_type, problem_type)


def _rank_key(suggestion):
    mode_rank = {"safe": 0, "smart": 1, "reconstruction": 2}
    risk_rank = {"low": 0, "medium": 1, "high": 2}
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    diff_hint = suggestion.get("_visual_diff_score", 0)
    return (
        priority_rank.get(suggestion["priority"], 2),
        mode_rank.get(suggestion["mode"], 9),
        risk_rank.get(suggestion["risk"], 9),
        -suggestion["estimated_layer_saving"],
        -diff_hint,
        -len(suggestion["current_layers"]),
    )


def _assign_ids(suggestions):
    for index, suggestion in enumerate(suggestions, start=1):
        suggestion["suggestion_id"] = f"suggestion_{index:04d}"
    return suggestions


def _strip_internal_fields(suggestions):
    for suggestion in suggestions:
        suggestion.pop("_visual_diff_score", None)
    return suggestions
