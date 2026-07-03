import json
from collections import Counter, defaultdict
from pathlib import Path


TYPE_NAMES = {
    1: "rectangle",
    2: "rotated_rectangle",
    16: "rotated_ellipse",
    32: "triangle",
    64: "line_internal_only",
    0xE4: "gradient_glow",
    0xE2: "gradient_disk",
}


INTERPRETATION_HINTS = {
    "1": [
        "TypeRectangle with 4 values may be x/y/width/height.",
        "TypeRectangle with 4 values may also be x1/y1/x2/y2.",
        "If used as a background, compare both interpretations before changing the renderer.",
    ],
    "2": [
        "TypeRotatedRectangle with 5 values may be cx/cy/halfW/halfH/theta.",
        "Some data may omit the unused sixth slot found in candidate internals.",
    ],
    "16": [
        "TypeRotatedEllipse with 5 values may be cx/cy/rx/ry/theta.",
        "Rotation and center semantics must be confirmed against Paint Studio preview.",
    ],
    "32": [
        "TypeTriangle with 6 values likely means x1/y1/x2/y2/x3/y3.",
        "Triangle rendering is a likely mismatch source if normalized bbox rendering is used.",
    ],
}


def analyze_geometry_semantics(geometry_path: str, output_dir: str) -> dict:
    geometry_file = Path(geometry_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    data = json.loads(geometry_file.read_text(encoding="utf-8"))
    shapes = data.get("shapes", [])
    if not isinstance(shapes, list):
        raise ValueError("Paint Studio geometry must contain a top-level shapes list.")

    by_type = defaultdict(list)
    for index, shape in enumerate(shapes):
        if isinstance(shape, dict):
            by_type[_shape_type(shape)].append((index, shape))

    type_reports = {}
    for shape_type, indexed_shapes in sorted(by_type.items()):
        type_reports[str(shape_type)] = _type_report(shape_type, indexed_shapes)

    report = {
        "geometry_path": str(geometry_file),
        "total_shapes": len(shapes),
        "shape_type_counts": {str(key): len(value) for key, value in sorted(by_type.items())},
        "type_reports": type_reports,
        "interpretation_hints": INTERPRETATION_HINTS,
        "global_observations": _global_observations(shapes),
    }

    (output_path / "geometry_semantics_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (output_path / "geometry_semantics_summary.txt").write_text(
        _summary_text(report),
        encoding="utf-8",
    )
    return report


def _type_report(shape_type, indexed_shapes):
    data_lengths = Counter()
    data_by_index = defaultdict(list)
    color_lengths = Counter()
    alpha_values = []
    scores = []
    layer_indices = []
    coordinate_values = []
    size_values = []
    rotation_values = []
    sample_data = []
    color_samples = []
    score_samples = []
    layer_index_samples = []

    for index, shape in indexed_shapes:
        layer_indices.append(index)
        if len(layer_index_samples) < 10:
            layer_index_samples.append(index)

        raw_data = shape.get("data")
        if isinstance(raw_data, list):
            data_lengths[str(len(raw_data))] += 1
            numeric_data = [_number(value) for value in raw_data]
            if len(sample_data) < 10:
                sample_data.append(raw_data)
            for data_index, value in enumerate(numeric_data):
                data_by_index[str(data_index)].append(value)
            coordinate_values.extend(numeric_data)
            if len(numeric_data) >= 4:
                size_values.extend([abs(numeric_data[2]), abs(numeric_data[3])])
            if len(numeric_data) >= 5:
                rotation_values.append(numeric_data[4])
        else:
            data_lengths["missing"] += 1

        color = shape.get("color")
        if isinstance(color, list):
            color_lengths[str(len(color))] += 1
            if len(color_samples) < 10:
                color_samples.append(color)
            if len(color) >= 4:
                alpha_values.append(_number(color[3]))
        else:
            color_lengths["missing"] += 1

        score = shape.get("score")
        if score is not None:
            score_value = _number(score)
            scores.append(score_value)
            if len(score_samples) < 10:
                score_samples.append(score_value)

    return {
        "type": shape_type,
        "type_name": TYPE_NAMES.get(shape_type, "mask_or_unknown"),
        "count": len(indexed_shapes),
        "data_length_distribution": dict(sorted(data_lengths.items())),
        "first_10_sample_data_arrays": sample_data,
        "data_index_stats": {
            key: _stats(values)
            for key, values in sorted(data_by_index.items(), key=lambda item: int(item[0]))
        },
        "color_array_length_distribution": dict(sorted(color_lengths.items())),
        "color_samples": color_samples,
        "alpha_statistics": _stats(alpha_values),
        "alpha_distribution": _alpha_distribution(alpha_values),
        "score_statistics": _stats(scores),
        "score_samples": score_samples,
        "layer_index_samples": layer_index_samples,
        "layer_index_range": _range(layer_indices),
        "coordinate_range": _range(coordinate_values),
        "size_radius_range": _range(size_values),
        "rotation_range": _range(rotation_values),
    }


def _global_observations(shapes):
    first_shape = shapes[0] if shapes and isinstance(shapes[0], dict) else None
    return {
        "first_shape_type": _shape_type(first_shape) if first_shape else None,
        "first_shape_data": first_shape.get("data") if first_shape else None,
        "first_shape_color": first_shape.get("color") if first_shape else None,
        "first_shape_may_be_background": _first_shape_may_be_background(first_shape),
        "score_order": _score_order(shapes),
    }


def _first_shape_may_be_background(shape):
    if not isinstance(shape, dict):
        return False
    if _shape_type(shape) != 1:
        return False
    data = shape.get("data")
    return isinstance(data, list) and len(data) == 4


def _score_order(shapes):
    scores = [
        _number(shape.get("score"))
        for shape in shapes
        if isinstance(shape, dict) and shape.get("score") is not None
    ]
    if len(scores) < 2:
        return "unknown"
    if all(a <= b for a, b in zip(scores, scores[1:])):
        return "ascending"
    if all(a >= b for a, b in zip(scores, scores[1:])):
        return "descending"
    return "mixed"


def _summary_text(report):
    lines = [
        "Paint Studio Geometry Semantics Summary",
        "",
        f"Geometry: {report['geometry_path']}",
        f"Total shapes: {report['total_shapes']}",
        f"Shape type counts: {report['shape_type_counts']}",
        "",
        "Global observations:",
    ]
    observations = report["global_observations"]
    for key, value in observations.items():
        lines.append(f"- {key}: {value}")

    lines.append("")
    lines.append("By shape type:")
    for type_id, type_report in report["type_reports"].items():
        lines.extend(
            [
                "",
                f"Type {type_id} ({type_report['type_name']})",
                f"- count: {type_report['count']}",
                f"- data lengths: {type_report['data_length_distribution']}",
                f"- layer index range: {type_report['layer_index_range']}",
                f"- coordinate range: {type_report['coordinate_range']}",
                f"- size/radius range: {type_report['size_radius_range']}",
                f"- rotation range: {type_report['rotation_range']}",
                f"- alpha stats: {type_report['alpha_statistics']}",
                f"- score stats: {type_report['score_statistics']}",
                f"- sample data: {type_report['first_10_sample_data_arrays'][:3]}",
            ]
        )
    return "\n".join(lines)


def _alpha_distribution(values):
    buckets = Counter()
    for value in values:
        if value <= 0:
            buckets["0"] += 1
        elif value < 64:
            buckets["1-63"] += 1
        elif value < 128:
            buckets["64-127"] += 1
        elif value < 192:
            buckets["128-191"] += 1
        elif value < 255:
            buckets["192-254"] += 1
        else:
            buckets["255"] += 1
    return dict(sorted(buckets.items()))


def _stats(values):
    numeric = [value for value in values if value is not None]
    if not numeric:
        return {"min": None, "max": None, "mean": None}
    return {
        "min": min(numeric),
        "max": max(numeric),
        "mean": round(sum(numeric) / len(numeric), 4),
    }


def _range(values):
    numeric = [value for value in values if value is not None]
    if not numeric:
        return {"min": None, "max": None}
    return {"min": min(numeric), "max": max(numeric)}


def _shape_type(shape):
    if not isinstance(shape, dict):
        return 0
    try:
        return int(shape.get("type"))
    except (TypeError, ValueError):
        return 0


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
