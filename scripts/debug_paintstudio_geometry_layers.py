import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.diagnostics.paint_studio_geometry_semantics import analyze_geometry_semantics
from engine.parser.paint_studio_geometry_parser import parse_paint_studio_geometry


SLICE_COUNTS = [1, 10, 50, 100, 250, 500, 1000]
TYPE_OUTPUTS = {
    1: "type_1_rectangle_only.png",
    2: "type_2_rotated_rectangle_only.png",
    16: "type_16_ellipse_only.png",
    32: "type_32_triangle_only.png",
}


def main():
    parser = argparse.ArgumentParser(
        description="Debug Paint Studio geometry semantics with layer slices and type isolation images."
    )
    parser.add_argument("--case", required=True, help="Case folder, for example cases/case_0001.")
    args = parser.parse_args()

    case_dir = Path(args.case)
    geometry_path = case_dir / "paintstudio_geometry.json"
    source_path = case_dir / "source_full.png"
    output_dir = case_dir / "geometry_debug"

    if not geometry_path.exists():
        print(f"Missing geometry: {geometry_path}")
        return 1
    if not source_path.exists():
        print(f"Missing source image: {source_path}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    report = analyze_geometry_semantics(str(geometry_path), str(output_dir))

    raw_geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    raw_shapes = raw_geometry.get("shapes", [])
    layers = parse_paint_studio_geometry(str(geometry_path))
    canvas_size = _image_size(source_path)

    _render_layer_slices(layers, output_dir / "layer_slices", canvas_size)
    _render_type_isolation(layers, output_dir / "type_isolation", canvas_size)
    _render_background_tests(raw_shapes, layers, output_dir / "background_tests", canvas_size)

    print(f"Geometry semantics debug written to {output_dir}")
    print(f"Total shapes: {report['total_shapes']}")
    print(f"Shape type counts: {report['shape_type_counts']}")
    print(f"First shape may be background: {report['global_observations']['first_shape_may_be_background']}")
    print(f"Score order: {report['global_observations']['score_order']}")
    return 0


def _render_layer_slices(layers, output_dir, canvas_size):
    output_dir.mkdir(parents=True, exist_ok=True)
    for count in SLICE_COUNTS:
        if count <= len(layers):
            _render_layers_fast(layers[:count], canvas_size, output_dir / f"first_{count:03d}_layers.png")
    _render_layers_fast(layers, canvas_size, output_dir / "all_layers.png")

    for count in [1, 10, 50, 100]:
        if count <= len(layers):
            _render_layers_fast(layers[-count:], canvas_size, output_dir / f"last_{count:03d}_layers.png")


def _render_type_isolation(layers, output_dir, canvas_size):
    output_dir.mkdir(parents=True, exist_ok=True)
    for type_id, filename in TYPE_OUTPUTS.items():
        selected = [layer for layer in layers if _raw_type(layer) == type_id]
        _render_layers_fast(selected, canvas_size, output_dir / filename)


def _render_background_tests(raw_shapes, layers, output_dir, canvas_size):
    output_dir.mkdir(parents=True, exist_ok=True)
    if not raw_shapes:
        return

    first = raw_shapes[0]
    if not isinstance(first, dict) or int(first.get("type", 0)) != 1:
        _render_layers_fast(layers, canvas_size, output_dir / "background_ignored.png", skip_first=True)
        return

    rest = layers[1:]
    background_data = first.get("data") if isinstance(first.get("data"), list) else []
    background_color = _rgba_from_raw_color(first.get("color"))

    _render_background_variant(background_data, background_color, rest, canvas_size, output_dir / "background_as_xywh.png", "xywh")
    _render_background_variant(background_data, background_color, rest, canvas_size, output_dir / "background_as_xyxy.png", "xyxy")
    _render_layers_fast(rest, canvas_size, output_dir / "background_ignored.png")


def _render_background_variant(data, color, rest_layers, canvas_size, output_path, mode):
    image, draw = _blank_canvas(canvas_size)
    if len(data) >= 4:
        x1 = _number(data[0])
        y1 = _number(data[1])
        if mode == "xywh":
            box = _box(x1, y1, _number(data[2]), _number(data[3]))
        else:
            x2 = _number(data[2])
            y2 = _number(data[3])
            box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        draw.rectangle(box, fill=color)
    _draw_layers(draw, rest_layers)
    image.save(output_path)


def _render_layers_fast(layers, canvas_size, output_path, skip_first=False):
    image, draw = _blank_canvas(canvas_size)
    selected = layers[1:] if skip_first else layers
    _draw_layers(draw, selected)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def _draw_layers(draw, layers):
    for layer in layers:
        shape = str(layer.get("shape", "")).lower()
        color = _rgba(layer.get("color"), layer.get("opacity", 1.0))
        x = _number(layer.get("x"))
        y = _number(layer.get("y"))
        width = _number(layer.get("width"))
        height = _number(layer.get("height"))
        box = _box(x, y, width, height)

        if shape in {"rectangle", "square"}:
            draw.rectangle(box, fill=color)
        elif shape in {"circle", "ellipse", "glow", "disk"}:
            draw.ellipse(box, fill=color)
        elif shape == "triangle":
            points = _triangle_points(layer, x, y, width, height)
            draw.polygon(points, fill=color)
        elif shape in {"line", "line_internal_only"}:
            thickness = max(1, int(min(abs(width), abs(height)) or 1))
            draw.line((x, y, x + width, y + height), fill=color, width=thickness)
        else:
            draw.rectangle(box, outline=(255, 0, 255, 180), fill=(255, 0, 255, 45), width=2)


def _triangle_points(layer, x, y, width, height):
    data = layer.get("raw", {}).get("data")
    if isinstance(data, list) and len(data) >= 6:
        return [
            (_number(data[0]), _number(data[1])),
            (_number(data[2]), _number(data[3])),
            (_number(data[4]), _number(data[5])),
        ]
    return [(x + width / 2, y), (x, y + height), (x + width, y + height)]


def _blank_canvas(canvas_size):
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Please install Pillow with: pip install pillow") from exc
    image = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
    return image, ImageDraw.Draw(image, "RGBA")


def _image_size(path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Please install Pillow with: pip install pillow") from exc
    with Image.open(path) as image:
        return image.size


def _raw_type(layer):
    try:
        return int(layer.get("raw", {}).get("type"))
    except (TypeError, ValueError):
        return 0


def _rgba_from_raw_color(color):
    if not isinstance(color, list):
        return (0, 0, 0, 255)
    r = _channel(color[0] if len(color) > 0 else 0)
    g = _channel(color[1] if len(color) > 1 else 0)
    b = _channel(color[2] if len(color) > 2 else 0)
    a = _channel(color[3] if len(color) > 3 else 255)
    return (r, g, b, a)


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


def _channel(value):
    return max(0, min(255, int(_number(value))))


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
