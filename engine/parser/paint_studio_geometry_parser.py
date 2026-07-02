import json
from pathlib import Path


class PaintStudioGeometryParseError(Exception):
    pass


TYPE_RECTANGLE = 1
TYPE_ROTATED_RECTANGLE = 2
TYPE_ROTATED_ELLIPSE = 16
TYPE_TRIANGLE = 32
TYPE_LINE = 64
TYPE_GRAD_GLOW = 0xE4
TYPE_GRAD_DISK = 0xE2


TYPE_TO_SHAPE = {
    TYPE_RECTANGLE: "rectangle",
    TYPE_ROTATED_RECTANGLE: "rectangle",
    TYPE_ROTATED_ELLIPSE: "ellipse",
    TYPE_TRIANGLE: "triangle",
    TYPE_LINE: "line_internal_only",
    TYPE_GRAD_GLOW: "glow",
    TYPE_GRAD_DISK: "disk",
}


def parse_paint_studio_geometry(path: str) -> list:
    source_path = Path(path)
    if not source_path.exists():
        raise PaintStudioGeometryParseError(f"Input file not found: {source_path}")

    try:
        data = json.loads(source_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise PaintStudioGeometryParseError(
            f"Could not parse Paint Studio geometry JSON: {source_path}"
        ) from exc

    if not looks_like_paint_studio_geometry(data):
        raise PaintStudioGeometryParseError(
            "Input JSON does not look like Paint Studio geometry. Expected top-level 'shapes' list."
        )

    return [_normalize_shape(shape, index) for index, shape in enumerate(data["shapes"])]


def looks_like_paint_studio_geometry(data) -> bool:
    if not isinstance(data, dict):
        return False
    shapes = data.get("shapes")
    if not isinstance(shapes, list):
        return False
    if not shapes:
        return True
    return all(isinstance(shape, dict) and "type" in shape and "data" in shape for shape in shapes)


def _normalize_shape(shape, index):
    shape_type = _int(shape.get("type"))
    shape_name = TYPE_TO_SHAPE.get(shape_type, "mask_or_unknown")
    raw_data = shape.get("data") if isinstance(shape.get("data"), list) else []
    color, opacity = _normalize_color(shape.get("color"))

    geometry = _geometry_for_shape(shape_name, raw_data)

    return {
        "id": str(shape.get("id") or f"paintstudio_shape_{index + 1}"),
        "shape": shape_name,
        "x": geometry["x"],
        "y": geometry["y"],
        "width": geometry["width"],
        "height": geometry["height"],
        "rotation": geometry["rotation"],
        "color": color,
        "opacity": opacity,
        "raw": shape,
    }


def _geometry_for_shape(shape_name, data):
    if shape_name in {"rectangle", "ellipse", "glow", "disk"} and len(data) >= 5:
        return _center_half_extent_geometry(data)

    if shape_name == "triangle" and len(data) >= 6:
        return _triangle_geometry(data)

    if shape_name == "line_internal_only" and len(data) >= 5:
        return _line_geometry(data)

    return _best_effort_geometry(data)


def _center_half_extent_geometry(data):
    cx = _number(data[0])
    cy = _number(data[1])
    half_w = abs(_number(data[2]))
    half_h = abs(_number(data[3]))
    return {
        "x": cx,
        "y": cy,
        "width": half_w * 2,
        "height": half_h * 2,
        "rotation": _number(data[4]),
    }


def _triangle_geometry(data):
    points = [
        (_number(data[0]), _number(data[1])),
        (_number(data[2]), _number(data[3])),
        (_number(data[4]), _number(data[5])),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    return {
        "x": sum(xs) / 3,
        "y": sum(ys) / 3,
        "width": max_x - min_x,
        "height": max_y - min_y,
        "rotation": 0.0,
    }


def _line_geometry(data):
    x1 = _number(data[0])
    y1 = _number(data[1])
    x2 = _number(data[2])
    y2 = _number(data[3])
    half_width = abs(_number(data[4]))
    return {
        "x": x1,
        "y": y1,
        "width": x2 - x1,
        "height": y2 - y1,
        "rotation": 0.0,
        "thickness": max(1.0, half_width * 2),
    }


def _best_effort_geometry(data):
    if len(data) >= 5:
        return _center_half_extent_geometry(data)
    if len(data) >= 4:
        x = _number(data[0])
        y = _number(data[1])
        return {
            "x": x,
            "y": y,
            "width": abs(_number(data[2])),
            "height": abs(_number(data[3])),
            "rotation": 0.0,
        }
    if len(data) >= 2:
        return {
            "x": _number(data[0]),
            "y": _number(data[1]),
            "width": 0.0,
            "height": 0.0,
            "rotation": 0.0,
        }
    return {
        "x": 0.0,
        "y": 0.0,
        "width": 0.0,
        "height": 0.0,
        "rotation": 0.0,
    }


def _normalize_color(value):
    if not isinstance(value, list):
        return "#000000", 1.0

    channels = [_int(channel) for channel in value]
    r = _clamp_channel(channels[0] if len(channels) > 0 else 0)
    g = _clamp_channel(channels[1] if len(channels) > 1 else 0)
    b = _clamp_channel(channels[2] if len(channels) > 2 else 0)
    opacity = 1.0
    if len(channels) > 3:
        opacity = max(0.0, min(1.0, channels[3] / 255))
    return f"#{r:02x}{g:02x}{b:02x}", opacity


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


def _clamp_channel(value):
    return max(0, min(255, value))
