import copy
import json
import shutil
from collections import Counter
from pathlib import Path

from engine.parser.paint_studio_geometry_parser import TYPE_TO_SHAPE, parse_paint_studio_geometry
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview


VARIANT_FILENAMES = {
    "current_renderer": "current_renderer.png",
    "reversed_layer_order": "reversed_layer_order.png",
    "rgb_no_alpha_test": "rgb_no_alpha_test.png",
    "bgr_channel_test": "bgr_channel_test.png",
    "alpha_ignored_test": "alpha_ignored_test.png",
    "alpha_inverted_test": "alpha_inverted_test.png",
    "source_grounded_renderer": "source_grounded_renderer.png",
}


def diagnose_paint_studio_geometry(
    geometry_path: str,
    source_image_path: str | None = None,
    paintstudio_preview_path: str | None = None,
    output_dir: str | None = None,
) -> dict:
    geometry_file = Path(geometry_path)
    output_path = Path(output_dir) if output_dir else geometry_file.parent / "renderer_diagnostic"
    render_dir = output_path / "render_variants"
    output_path.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    raw_geometry = _load_geometry(geometry_file)
    raw_shapes = raw_geometry.get("shapes", [])
    layers = parse_paint_studio_geometry(str(geometry_file))
    canvas_info = _canvas_info(source_image_path, paintstudio_preview_path)

    shape_stats = _shape_stats(raw_shapes, canvas_info)
    variant_paths, source_renderer_metadata = _render_variants(layers, canvas_info, render_dir, geometry_file)
    comparisons = _compare_variants(variant_paths, source_image_path, paintstudio_preview_path)
    warning = _renderer_warning(shape_stats, comparisons)

    report = {
        "geometry_path": str(geometry_file),
        "source_image_path": str(source_image_path) if source_image_path else None,
        "paintstudio_preview_path": str(paintstudio_preview_path) if paintstudio_preview_path else None,
        "output_dir": str(output_path),
        "renderer_compatibility_warning": warning,
        "likely_causes": _likely_causes(shape_stats, comparisons),
        "shape_diagnostics": shape_stats,
        "render_variants": variant_paths,
        "source_grounded_renderer_metadata": source_renderer_metadata,
        "comparisons": comparisons,
        "notes": [
            "This diagnostic is read-only. It does not modify geometry or the default FLO renderer.",
            "current_renderer.png reuses case flo_preview.png when available; other variants use a faster diagnostic renderer.",
            "Paint Studio preview comparison is the main renderer compatibility signal when dimensions match.",
            "Source image comparison is useful context, but it is not the same as Paint Studio preview comparison.",
        ],
    }

    _write_outputs(report, output_path)
    return report


def _load_geometry(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
        raise ValueError(f"Paint Studio geometry must contain a top-level shapes list: {path}")
    return data


def _canvas_info(source_image_path, paintstudio_preview_path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Please install Pillow with: pip install pillow") from exc

    for candidate in (source_image_path, paintstudio_preview_path):
        if candidate and Path(candidate).exists():
            with Image.open(candidate) as image:
                width, height = image.size
            return {"size": {"width": width, "height": height}}
    return {"size": {"width": 1000, "height": 1000}}


def _shape_stats(shapes, canvas_info):
    shape_types = [_int(shape.get("type")) for shape in shapes if isinstance(shape, dict)]
    known_types = set(TYPE_TO_SHAPE)
    unknown_types = [shape_type for shape_type in shape_types if shape_type not in known_types]
    mask_like_types = [shape_type for shape_type in unknown_types if shape_type >= 64]
    color_lengths = Counter()
    alpha_values = []
    scores = []
    data_lengths = Counter()
    all_coords = []
    size_values = []
    rotations = []
    locked_count = 0

    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        color = shape.get("color")
        if isinstance(color, list):
            color_lengths[str(len(color))] += 1
            if len(color) >= 4:
                alpha_values.append(_number(color[3]))
            else:
                alpha_values.append(None)
        else:
            color_lengths["missing"] += 1
            alpha_values.append(None)

        score = shape.get("score")
        if score is not None:
            scores.append(_number(score))

        if shape.get("locked"):
            locked_count += 1

        data = shape.get("data")
        if isinstance(data, list):
            data_lengths[str(len(data))] += 1
            numbers = [_number(value) for value in data]
            all_coords.extend(numbers)
            if len(numbers) >= 4:
                size_values.extend([abs(numbers[2]), abs(numbers[3])])
            if len(numbers) >= 5:
                rotations.append(numbers[4])
        else:
            data_lengths["missing"] += 1

    return {
        "total_shape_count": len(shapes),
        "shape_type_counts": _count_as_dict(shape_types),
        "mapped_shape_counts": _mapped_shape_counts(shape_types),
        "unknown_type_count": len(unknown_types),
        "unknown_type_counts": _count_as_dict(unknown_types),
        "mask_like_type_count": len(mask_like_types),
        "mask_like_type_counts": _count_as_dict(mask_like_types),
        "color_array_length_distribution": dict(sorted(color_lengths.items())),
        "alpha_value_distribution": _alpha_distribution(alpha_values),
        "score_range": _range(scores),
        "locked_count": locked_count,
        "data_array_length_distribution": dict(sorted(data_lengths.items())),
        "coordinate_range": _range(all_coords),
        "size_radius_range": _range(size_values),
        "rotation_range": _range(rotations),
        "first_shape_background": _first_shape_background(shapes, canvas_info),
        "layer_order_inference": _layer_order_inference(shapes, canvas_info),
    }


def _render_variants(layers, image_info, render_dir, geometry_file):
    variants = {
        "reversed_layer_order": list(reversed(copy.deepcopy(layers))),
        "rgb_no_alpha_test": _force_alpha(layers, opacity=1.0),
        "bgr_channel_test": _bgr_layers(layers),
        "alpha_ignored_test": _alpha_ignored_non_background(layers),
        "alpha_inverted_test": _alpha_inverted(layers),
    }

    paths = {}
    current_path = render_dir / VARIANT_FILENAMES["current_renderer"]
    existing_flo_preview = geometry_file.parent / "flo_preview.png"
    if existing_flo_preview.exists():
        shutil.copyfile(existing_flo_preview, current_path)
    else:
        _render_layers_fast(layers, image_info, current_path)
    paths["current_renderer"] = str(current_path)

    for name, variant_layers in variants.items():
        output_path = render_dir / VARIANT_FILENAMES[name]
        _render_layers_fast(variant_layers, image_info, output_path)
        paths[name] = str(output_path)

    source_metadata = _render_source_grounded_variant(image_info, render_dir, geometry_file)
    source_output = render_dir / VARIANT_FILENAMES["source_grounded_renderer"]
    if source_output.exists():
        paths["source_grounded_renderer"] = str(source_output)
    return paths, source_metadata


def _render_source_grounded_variant(image_info, render_dir, geometry_file):
    size = image_info.get("size") or {}
    output_path = render_dir / VARIANT_FILENAMES["source_grounded_renderer"]
    try:
        return render_paint_studio_preview(
            str(geometry_file),
            str(output_path),
            width=int(size.get("width") or 0) or None,
            height=int(size.get("height") or 0) or None,
            ssaa=2,
        )
    except Exception as exc:
        return {
            "output_path": str(output_path),
            "render_failed": True,
            "error": str(exc),
        }


def _render_layers_fast(layers, image_info, output_path):
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Please install Pillow with: pip install pillow") from exc

    size = image_info.get("size") or {}
    width = int(size.get("width") or 1000)
    height = int(size.get("height") or 1000)
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    for layer in layers:
        shape = str(layer.get("shape", "")).lower()
        color = _rgba(layer.get("color"), layer.get("opacity", 1.0))
        x = _number(layer.get("x"))
        y = _number(layer.get("y"))
        layer_width = _number(layer.get("width"))
        layer_height = _number(layer.get("height"))
        box = _box(x, y, layer_width, layer_height)

        if shape in {"rectangle", "square"}:
            draw.rectangle(box, fill=color)
        elif shape in {"circle", "ellipse", "glow", "disk"}:
            draw.ellipse(box, fill=color)
        elif shape == "triangle":
            draw.polygon(
                [
                    (x + layer_width / 2, y),
                    (x, y + layer_height),
                    (x + layer_width, y + layer_height),
                ],
                fill=color,
            )
        elif shape in {"line", "line_internal_only"}:
            thickness = max(1, int(min(abs(layer_width), abs(layer_height)) or 1))
            draw.line((x, y, x + layer_width, y + layer_height), fill=color, width=thickness)
        else:
            draw.rectangle(box, outline=(255, 0, 255, 180), fill=(255, 0, 255, 45), width=2)
            draw.line((x, y, x + layer_width, y + layer_height), fill=(255, 0, 255, 180), width=1)
            draw.line((x + layer_width, y, x, y + layer_height), fill=(255, 0, 255, 180), width=1)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def _compare_variants(variant_paths, source_image_path, paintstudio_preview_path):
    comparisons = {
        "paintstudio_preview": _compare_against_target(variant_paths, paintstudio_preview_path, "paintstudio_preview"),
        "source_image": _compare_against_target(variant_paths, source_image_path, "source_image"),
        "source_comparison_note": "Source image comparison is not a Paint Studio renderer compatibility check.",
    }
    comparisons["closest_to_paintstudio_preview"] = _closest_variant(comparisons["paintstudio_preview"])
    comparisons["closest_to_source_image"] = _closest_variant(comparisons["source_image"])
    return comparisons


def _compare_against_target(variant_paths, target_path, target_name):
    if not target_path or not Path(target_path).exists():
        return {
            "target": target_name,
            "path": str(target_path) if target_path else None,
            "available": False,
            "reliable": False,
            "scores": {},
            "note": "Target image is not available.",
        }

    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise RuntimeError("Please install Pillow with: pip install pillow") from exc

    with Image.open(target_path) as target_image:
        target = target_image.convert("RGB")
        target_size = target.size

    scores = {}
    resized_any = False
    for variant_name, variant_path in variant_paths.items():
        with Image.open(variant_path) as variant_image:
            variant = variant_image.convert("RGB")
            resized = variant.size != target_size
            if resized:
                variant = variant.resize(target_size, Image.Resampling.BICUBIC)
                resized_any = True
            diff = ImageChops.difference(target, variant)
            scores[variant_name] = {
                "difference_score": _difference_score(diff),
                "variant_path": variant_path,
                "resized_for_score": resized,
            }

    return {
        "target": target_name,
        "path": str(target_path),
        "available": True,
        "reliable": not resized_any,
        "target_size": {"width": target_size[0], "height": target_size[1]},
        "scores": scores,
        "note": "Comparison is unreliable if any variant had to be resized.",
    }


def _write_outputs(report, output_path):
    report_path = output_path / "renderer_diagnostic_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    shape_stats = report["shape_diagnostics"]
    shape_lines = [
        "Paint Studio Shape Type Summary",
        "",
        f"Total shapes: {shape_stats['total_shape_count']}",
        f"Shape type counts: {shape_stats['shape_type_counts']}",
        f"Mapped shape counts: {shape_stats['mapped_shape_counts']}",
        f"Unknown type count: {shape_stats['unknown_type_count']}",
        f"Mask-like type count: {shape_stats['mask_like_type_count']}",
        f"Data length distribution: {shape_stats['data_array_length_distribution']}",
        f"Coordinate range: {shape_stats['coordinate_range']}",
        f"Size/radius range: {shape_stats['size_radius_range']}",
        f"Rotation range: {shape_stats['rotation_range']}",
        f"First shape background: {shape_stats['first_shape_background']}",
        f"Layer order inference: {shape_stats['layer_order_inference']}",
    ]
    (output_path / "shape_type_summary.txt").write_text("\n".join(shape_lines), encoding="utf-8")

    color_lines = [
        "Paint Studio Color / Alpha Summary",
        "",
        f"Color length distribution: {shape_stats['color_array_length_distribution']}",
        f"Alpha distribution: {shape_stats['alpha_value_distribution']}",
        f"Score range: {shape_stats['score_range']}",
        f"Locked count: {shape_stats['locked_count']}",
    ]
    (output_path / "color_alpha_summary.txt").write_text("\n".join(color_lines), encoding="utf-8")


def _renderer_warning(shape_stats, comparisons):
    warnings = []
    if shape_stats["unknown_type_count"] or shape_stats["mask_like_type_count"]:
        warnings.append("unsupported_or_mask_like_shape_types_detected")
    if _alpha_ambiguous(shape_stats["alpha_value_distribution"]):
        warnings.append("alpha_channel_interpretation_needs_check")

    paintstudio = comparisons.get("paintstudio_preview", {})
    if paintstudio.get("available"):
        best = _closest_variant(paintstudio)
        if best and best.get("difference_score", 0) >= 0.18:
            warnings.append("all_variants_far_from_paintstudio_preview")
        if not paintstudio.get("reliable"):
            warnings.append("paintstudio_preview_dimension_mismatch")

    return {
        "input_format": "paintstudio_geometry",
        "warning": bool(warnings),
        "reasons": warnings,
    }


def _likely_causes(shape_stats, comparisons):
    causes = []
    paintstudio = comparisons.get("paintstudio_preview", {})
    closest = _closest_variant(paintstudio)

    if paintstudio.get("available") and not paintstudio.get("reliable"):
        causes.append(
            {
                "cause": "canvas_or_preview_dimension_mismatch",
                "confidence": "high",
                "reason": "Paint Studio preview comparison required resizing, so it may be a UI screenshot, crop, or differently scaled export.",
            }
        )

    first_background = shape_stats.get("first_shape_background", {})
    first_data = first_background.get("data") or []
    if first_background.get("appears_background") and len(first_data) == 4:
        causes.append(
            {
                "cause": "type_rectangle_background_data_semantics",
                "confidence": "medium",
                "reason": "The first TypeRectangle background uses 4 data values, which may not match FLO's current center/half-extent assumption.",
            }
        )

    if closest and closest.get("variant") == "reversed_layer_order":
        causes.append(
            {
                "cause": "layer_order_mismatch_possible",
                "confidence": "medium",
                "reason": "The reversed layer order variant scored closest to Paint Studio preview.",
            }
        )

    alpha_distribution = shape_stats.get("alpha_value_distribution", {})
    if _alpha_ambiguous(alpha_distribution):
        causes.append(
            {
                "cause": "alpha_interpretation_ambiguity",
                "confidence": "medium",
                "reason": "Many shapes use intermediate alpha values, so opacity interpretation should be checked.",
            }
        )

    if shape_stats.get("mask_like_type_count"):
        causes.append(
            {
                "cause": "unsupported_mask_or_shape_words",
                "confidence": "medium",
                "reason": "Mask-like or unknown shape types were detected.",
            }
        )

    if not causes:
        causes.append(
            {
                "cause": "unknown",
                "confidence": "low",
                "reason": "No single strong cause was identified by this diagnostic.",
            }
        )
    return causes


def _closest_variant(comparison):
    scores = comparison.get("scores") if isinstance(comparison, dict) else None
    if not scores:
        return None
    name, data = min(scores.items(), key=lambda item: item[1]["difference_score"])
    return {
        "variant": name,
        "difference_score": data["difference_score"],
        "variant_path": data["variant_path"],
    }


def _force_alpha(layers, opacity):
    modified = copy.deepcopy(layers)
    for layer in modified:
        layer["opacity"] = opacity
    return modified


def _alpha_ignored_non_background(layers):
    modified = copy.deepcopy(layers)
    for index, layer in enumerate(modified):
        if index != 0:
            layer["opacity"] = 1.0
    return modified


def _alpha_inverted(layers):
    modified = copy.deepcopy(layers)
    for layer in modified:
        color = layer.get("raw", {}).get("color")
        if isinstance(color, list) and len(color) >= 4:
            layer["opacity"] = max(0.0, min(1.0, 1.0 - (_number(color[3]) / 255)))
    return modified


def _bgr_layers(layers):
    modified = copy.deepcopy(layers)
    for layer in modified:
        color = layer.get("color")
        if isinstance(color, str) and color.startswith("#") and len(color) == 7:
            layer["color"] = f"#{color[5:7]}{color[3:5]}{color[1:3]}"
    return modified


def _rgba(color, opacity):
    alpha = int(max(0.0, min(1.0, _number(opacity))) * 255)
    if isinstance(color, str) and color.startswith("#") and len(color) == 7:
        try:
            return (
                int(color[1:3], 16),
                int(color[3:5], 16),
                int(color[5:7], 16),
                alpha,
            )
        except ValueError:
            pass
    return (0, 0, 0, alpha)


def _box(x, y, width, height):
    return (
        min(x, x + width),
        min(y, y + height),
        max(x, x + width),
        max(y, y + height),
    )


def _mapped_shape_counts(shape_types):
    counts = Counter(TYPE_TO_SHAPE.get(shape_type, "mask_or_unknown") for shape_type in shape_types)
    return dict(sorted(counts.items()))


def _count_as_dict(values):
    return {str(key): value for key, value in sorted(Counter(values).items())}


def _alpha_distribution(alpha_values):
    buckets = Counter()
    numeric = []
    for alpha in alpha_values:
        if alpha is None:
            buckets["missing"] += 1
            continue
        numeric.append(alpha)
        if alpha <= 0:
            buckets["0"] += 1
        elif alpha < 64:
            buckets["1-63"] += 1
        elif alpha < 128:
            buckets["64-127"] += 1
        elif alpha < 192:
            buckets["128-191"] += 1
        elif alpha < 255:
            buckets["192-254"] += 1
        else:
            buckets["255"] += 1
    return {
        "buckets": dict(sorted(buckets.items())),
        "range": _range(numeric),
        "unique_count": len(set(numeric)),
    }


def _alpha_ambiguous(alpha_distribution):
    buckets = alpha_distribution.get("buckets", {})
    return any(bucket in buckets for bucket in ("1-63", "64-127", "128-191", "192-254"))


def _first_shape_background(shapes, canvas_info):
    if not shapes:
        return {"appears_background": False, "reason": "No shapes."}
    first = shapes[0]
    if not isinstance(first, dict):
        return {"appears_background": False, "reason": "First shape is not an object."}

    data = first.get("data")
    if not isinstance(data, list) or len(data) < 4:
        return {"appears_background": False, "reason": "First shape has no bbox-like data."}

    canvas = canvas_info.get("size") or {}
    width = _number(canvas.get("width"))
    height = _number(canvas.get("height"))
    half_w = abs(_number(data[2]))
    half_h = abs(_number(data[3]))
    covers_width = width > 0 and half_w * 2 >= width * 0.9
    covers_height = height > 0 and half_h * 2 >= height * 0.9
    appears = _int(first.get("type")) in {1, 2} and covers_width and covers_height
    return {
        "appears_background": appears,
        "reason": "First rectangle covers most of canvas." if appears else "First shape does not clearly cover canvas.",
        "shape_type": _int(first.get("type")),
        "data": data,
    }


def _layer_order_inference(shapes, canvas_info):
    first_background = _first_shape_background(shapes, canvas_info)
    score_order = _score_order(shapes)
    if first_background["appears_background"]:
        inferred = "likely_back_to_front"
    else:
        inferred = "unknown"
    return {
        "inferred_order": inferred,
        "score_order": score_order,
        "reason": "Background-like first shape suggests back-to-front painting." if inferred != "unknown" else "No strong layer order signal.",
    }


def _score_order(shapes):
    scores = [_number(shape.get("score")) for shape in shapes if isinstance(shape, dict) and shape.get("score") is not None]
    if len(scores) < 2:
        return "unknown"
    if all(a <= b for a, b in zip(scores, scores[1:])):
        return "ascending"
    if all(a >= b for a, b in zip(scores, scores[1:])):
        return "descending"
    return "mixed"


def _range(values):
    numeric = [value for value in values if value is not None]
    if not numeric:
        return {"min": None, "max": None}
    return {"min": min(numeric), "max": max(numeric)}


def _difference_score(diff):
    pixels = list(diff.getdata())
    if not pixels:
        return 0.0
    total = sum((r + g + b) / (255 * 3) for r, g, b in pixels)
    return round(total / len(pixels), 4)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
