import json
import math
from pathlib import Path


TYPE_RECTANGLE = 1
TYPE_ROTATED_RECTANGLE = 2
TYPE_ROTATED_ELLIPSE = 16
TYPE_TRIANGLE = 32


class PaintStudioSourceRenderError(Exception):
    pass


def render_paint_studio_preview(
    geometry_path: str,
    output_path: str,
    width: int | None = None,
    height: int | None = None,
    ssaa: int = 2,
    background_mode: str = "paintstudio",
) -> dict:
    try:
        from PIL import Image, ImageDraw
        import numpy as np
    except ImportError as exc:
        raise PaintStudioSourceRenderError(
            "Please install Pillow and numpy with: pip install pillow numpy"
        ) from exc

    if ssaa not in {1, 2, 4}:
        raise PaintStudioSourceRenderError("--ssaa must be 1, 2, or 4.")

    geometry_file = Path(geometry_path)
    geometry = _load_geometry(geometry_file)
    shapes = geometry.get("shapes", [])
    canvas_width, canvas_height, canvas_source, warnings = _resolve_canvas_size(
        geometry_file,
        geometry,
        width,
        height,
        Image,
    )

    canvas = _initial_canvas(shapes, canvas_width, canvas_height, background_mode, np)

    unsupported = {}
    rendered = 0
    skipped = 0

    for index, shape in enumerate(shapes):
        if index == 0 and background_mode == "paintstudio":
            skipped += 1
            continue

        shape_type = _int(shape.get("type"))
        data = shape.get("data") if isinstance(shape.get("data"), list) else []
        color = shape.get("color") if isinstance(shape.get("color"), list) else []
        alpha = _alpha(color)
        if alpha <= 0:
            skipped += 1
            continue

        coverage = None
        if shape_type == TYPE_ROTATED_RECTANGLE and len(data) >= 4:
            coverage = _rotated_rect_coverage(data, canvas_width, canvas_height, ssaa, np)
        elif shape_type == TYPE_ROTATED_ELLIPSE and len(data) >= 4:
            coverage = _rotated_ellipse_coverage(data, canvas_width, canvas_height, ssaa, np)
        elif shape_type == TYPE_TRIANGLE and len(data) >= 6:
            coverage = _triangle_coverage(data, canvas_width, canvas_height, ssaa, Image, ImageDraw, np)
        elif shape_type == TYPE_RECTANGLE:
            if len(data) >= 4:
                coverage = _axis_rect_coverage(data, canvas_width, canvas_height, ssaa, np)

        if coverage is None:
            unsupported[str(shape_type)] = unsupported.get(str(shape_type), 0) + 1
            skipped += 1
            continue

        if coverage["mask"].size == 0 or float(coverage["mask"].max()) <= 0:
            skipped += 1
            continue

        _blend(canvas, coverage, color, alpha, np)
        rendered += 1

    image = _linear_canvas_to_image(canvas, np, Image)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_file)

    return {
        "output_path": str(output_file),
        "canvas": {
            "width": canvas_width,
            "height": canvas_height,
            "source": canvas_source,
        },
        "total_shapes": len(shapes),
        "rendered_shape_count": rendered,
        "skipped_shape_count": skipped,
        "unsupported_shape_types": unsupported,
        "ssaa": ssaa,
        "blending_mode": "linear_light_source_over_rgb_output",
        "background_handling": background_mode,
        "warnings": warnings,
    }


def srgb_to_linear(value):
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def linear_to_srgb(value):
    if value <= 0.0031308:
        return value * 12.92
    return 1.055 * (value ** (1 / 2.4)) - 0.055


def source_over_linear(dst_linear, src_linear, effective_alpha):
    return src_linear * effective_alpha + dst_linear * (1.0 - effective_alpha)


def _load_geometry(path):
    if not path.exists():
        raise PaintStudioSourceRenderError(f"Geometry file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PaintStudioSourceRenderError(f"Could not parse geometry JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
        raise PaintStudioSourceRenderError("Paint Studio geometry must contain a top-level shapes list.")
    return data


def _resolve_canvas_size(geometry_file, geometry, width, height, image_module):
    warnings = []
    if width and height:
        return int(width), int(height), "explicit_args", warnings

    source_full = geometry_file.parent / "source_full.png"
    if source_full.exists():
        with image_module.open(source_full) as image:
            image_width, image_height = image.size
        return image_width, image_height, "case_source_full_png", warnings

    for key_pair in (("width", "height"), ("w", "h")):
        if geometry.get(key_pair[0]) and geometry.get(key_pair[1]):
            return int(geometry[key_pair[0]]), int(geometry[key_pair[1]]), "geometry_top_level", warnings

    meta_path = geometry_file.parent / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for key_pair in (("width", "height"), ("w", "h")):
                if meta.get(key_pair[0]) and meta.get(key_pair[1]):
                    return int(meta[key_pair[0]]), int(meta[key_pair[1]]), "meta_json", warnings
        except (OSError, ValueError):
            warnings.append(f"Could not read canvas size from {meta_path}.")

    shapes = geometry.get("shapes", [])
    if shapes:
        first = shapes[0]
        data = first.get("data") if isinstance(first, dict) else None
        if isinstance(data, list) and len(data) >= 4:
            inferred_width = int(round(abs(_number(data[2]))))
            inferred_height = int(round(abs(_number(data[3]))))
            if inferred_width > 0 and inferred_height > 0:
                warnings.append("Canvas size inferred from first background shape.")
                return inferred_width, inferred_height, "first_background_shape", warnings

    raise PaintStudioSourceRenderError(
        "Could not determine canvas size. Provide width/height or place source_full.png next to geometry."
    )


def _initial_canvas(shapes, width, height, background_mode, np):
    if background_mode != "paintstudio":
        raise PaintStudioSourceRenderError("Only background_mode='paintstudio' is supported in v0.5.9.")

    color = [255, 255, 255, 255]
    if shapes and isinstance(shapes[0], dict) and isinstance(shapes[0].get("color"), list):
        color = shapes[0]["color"]

    rgb = _srgb_color_to_linear(color, np)
    canvas = np.zeros((height, width, 3), dtype=np.float32)
    canvas[:, :, 0] = rgb[0]
    canvas[:, :, 1] = rgb[1]
    canvas[:, :, 2] = rgb[2]
    return canvas


def _rotated_rect_coverage(data, width, height, ssaa, np):
    cx = _number(data[0])
    cy = _number(data[1])
    half_w = abs(_number(data[2]))
    half_h = abs(_number(data[3]))
    theta = _number(data[4]) if len(data) >= 5 else 0.0
    bbox = _rotated_extent_bbox(cx, cy, half_w, half_h, theta, width, height)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    xs, ys = _sample_grid(x0, y0, x1, y1, ssaa, np)
    dx = xs - cx
    dy = ys - cy
    radians = math.radians(theta)
    cos_t = math.cos(radians)
    sin_t = math.sin(radians)
    xr = dx * cos_t + dy * sin_t
    yr = -dx * sin_t + dy * cos_t
    inside = (np.abs(xr) <= half_w) & (np.abs(yr) <= half_h)
    return _coverage_from_inside(inside, x0, y0, ssaa, np)


def _rotated_ellipse_coverage(data, width, height, ssaa, np):
    cx = _number(data[0])
    cy = _number(data[1])
    rx = abs(_number(data[2]))
    ry = abs(_number(data[3]))
    theta = _number(data[4]) if len(data) >= 5 else 0.0
    if rx <= 0 or ry <= 0:
        return None
    bbox = _rotated_extent_bbox(cx, cy, rx, ry, theta, width, height)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    xs, ys = _sample_grid(x0, y0, x1, y1, ssaa, np)
    dx = xs - cx
    dy = ys - cy
    radians = math.radians(theta)
    cos_t = math.cos(radians)
    sin_t = math.sin(radians)
    xr = dx * cos_t + dy * sin_t
    yr = -dx * sin_t + dy * cos_t
    inside = (xr * xr) / (rx * rx) + (yr * yr) / (ry * ry) <= 1.0
    return _coverage_from_inside(inside, x0, y0, ssaa, np)


def _triangle_coverage(data, width, height, ssaa, image_module, image_draw, np):
    points = [
        (_number(data[0]), _number(data[1])),
        (_number(data[2]), _number(data[3])),
        (_number(data[4]), _number(data[5])),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bbox = _clip_bbox(
        math.floor(min(xs)) - 1,
        math.floor(min(ys)) - 1,
        math.ceil(max(xs)) + 1,
        math.ceil(max(ys)) + 1,
        width,
        height,
    )
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    mask = image_module.new("L", ((x1 - x0) * ssaa, (y1 - y0) * ssaa), 0)
    draw = image_draw.Draw(mask)
    scaled = [((x - x0) * ssaa, (y - y0) * ssaa) for x, y in points]
    draw.polygon(scaled, fill=255)
    high = np.asarray(mask, dtype=np.float32) / 255.0
    coverage = high.reshape(y1 - y0, ssaa, x1 - x0, ssaa).mean(axis=(1, 3))
    return {"x0": x0, "y0": y0, "mask": coverage}


def _axis_rect_coverage(data, width, height, ssaa, np):
    x = _number(data[0])
    y = _number(data[1])
    rect_width = _number(data[2])
    rect_height = _number(data[3])
    bbox = _clip_bbox(
        math.floor(min(x, x + rect_width)) - 1,
        math.floor(min(y, y + rect_height)) - 1,
        math.ceil(max(x, x + rect_width)) + 1,
        math.ceil(max(y, y + rect_height)) + 1,
        width,
        height,
    )
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    xs, ys = _sample_grid(x0, y0, x1, y1, ssaa, np)
    inside = (
        (xs >= min(x, x + rect_width))
        & (xs <= max(x, x + rect_width))
        & (ys >= min(y, y + rect_height))
        & (ys <= max(y, y + rect_height))
    )
    return _coverage_from_inside(inside, x0, y0, ssaa, np)


def _rotated_extent_bbox(cx, cy, half_w, half_h, theta, width, height):
    radians = math.radians(theta)
    cos_t = abs(math.cos(radians))
    sin_t = abs(math.sin(radians))
    extent_x = half_w * cos_t + half_h * sin_t
    extent_y = half_w * sin_t + half_h * cos_t
    return _clip_bbox(
        math.floor(cx - extent_x) - 1,
        math.floor(cy - extent_y) - 1,
        math.ceil(cx + extent_x) + 1,
        math.ceil(cy + extent_y) + 1,
        width,
        height,
    )


def _clip_bbox(x0, y0, x1, y1, width, height):
    x0 = max(0, int(x0))
    y0 = max(0, int(y0))
    x1 = min(width, int(x1))
    y1 = min(height, int(y1))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _sample_grid(x0, y0, x1, y1, ssaa, np):
    xs = (np.arange(x0 * ssaa, x1 * ssaa, dtype=np.float32) + 0.5) / ssaa
    ys = (np.arange(y0 * ssaa, y1 * ssaa, dtype=np.float32) + 0.5) / ssaa
    return np.meshgrid(xs, ys)


def _coverage_from_inside(inside, x0, y0, ssaa, np):
    height_ss, width_ss = inside.shape
    height = height_ss // ssaa
    width = width_ss // ssaa
    coverage = inside.astype(np.float32).reshape(height, ssaa, width, ssaa).mean(axis=(1, 3))
    return {"x0": x0, "y0": y0, "mask": coverage}


def _blend(canvas, coverage, color, alpha, np):
    mask = coverage["mask"]
    x0 = coverage["x0"]
    y0 = coverage["y0"]
    height, width = mask.shape
    region = canvas[y0 : y0 + height, x0 : x0 + width, :]
    effective_alpha = (mask * alpha).astype(np.float32)
    src = _srgb_color_to_linear(color, np).reshape((1, 1, 3))
    region[:] = source_over_linear(region, src, effective_alpha[:, :, None])


def _linear_canvas_to_image(canvas, np, image_module):
    vectorized = np.vectorize(linear_to_srgb)
    srgb = vectorized(np.clip(canvas, 0.0, 1.0))
    bytes_rgb = np.clip(np.rint(srgb * 255.0), 0, 255).astype("uint8")
    return image_module.fromarray(bytes_rgb, "RGB")


def _srgb_color_to_linear(color, np):
    channels = [_channel(color, 0), _channel(color, 1), _channel(color, 2)]
    srgb = np.array(channels, dtype=np.float32) / 255.0
    return np.array([srgb_to_linear(float(value)) for value in srgb], dtype=np.float32)


def _alpha(color):
    if not isinstance(color, list) or len(color) < 4:
        return 1.0
    return max(0.0, min(1.0, _number(color[3]) / 255.0))


def _channel(color, index):
    if not isinstance(color, list) or len(color) <= index:
        return 0
    return max(0, min(255, _int(color[index])))


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
