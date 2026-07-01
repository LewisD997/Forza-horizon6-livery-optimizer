from pathlib import Path


SUPPORTED_SHAPES = {"rectangle", "square", "circle", "ellipse", "triangle", "line"}


class PreviewRenderError(Exception):
    pass


def render_preview(layers, image_info, output_path):
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise PreviewRenderError("Please install Pillow with: pip install pillow") from exc

    size = image_info.get("size") or {}
    width = int(size.get("width") or 1000)
    height = int(size.get("height") or 1000)
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))

    notes = []
    for layer in layers:
        shape = layer["shape"].lower()
        if shape not in SUPPORTED_SHAPES:
            _draw_unknown_shape(canvas, ImageDraw, layer)
            notes.append(
                f"Unknown shape '{layer['shape']}' rendered as debug bounding box for layer {layer['id']}."
            )
            continue

        layer_image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(layer_image, "RGBA")
        color = _rgba(layer["color"], layer["opacity"])

        if shape in {"rectangle", "square"}:
            _draw_rectangle(draw, layer, color, force_square=(shape == "square"))
        elif shape in {"circle", "ellipse"}:
            _draw_ellipse(draw, layer, color, force_circle=(shape == "circle"))
        elif shape == "triangle":
            _draw_triangle(draw, layer, color)
        elif shape == "line":
            _draw_line(draw, layer, color)

        if layer["rotation"]:
            layer_image = layer_image.rotate(
                -layer["rotation"],
                center=_center(layer),
                resample=Image.Resampling.BICUBIC,
            )

        canvas.alpha_composite(layer_image)

    preview_path = Path(output_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGBA").save(preview_path)

    return {
        "preview_path": str(preview_path),
        "notes": notes,
    }


def _draw_rectangle(draw, layer, color, force_square=False):
    x, y, width, height = _box_values(layer)
    if force_square:
        side = min(abs(width), abs(height))
        width = side if width >= 0 else -side
        height = side if height >= 0 else -side
    draw.rectangle(_box(x, y, width, height), fill=color)


def _draw_ellipse(draw, layer, color, force_circle=False):
    x, y, width, height = _box_values(layer)
    if force_circle:
        side = min(abs(width), abs(height))
        width = side if width >= 0 else -side
        height = side if height >= 0 else -side
    draw.ellipse(_box(x, y, width, height), fill=color)


def _draw_triangle(draw, layer, color):
    x, y, width, height = _box_values(layer)
    points = [
        (x + width / 2, y),
        (x, y + height),
        (x + width, y + height),
    ]
    draw.polygon(points, fill=color)


def _draw_line(draw, layer, color):
    x, y, width, height = _box_values(layer)
    thickness = max(1, int(min(abs(width), abs(height)) or layer["raw"].get("thickness", 1)))
    draw.line((x, y, x + width, y + height), fill=color, width=thickness)


def _draw_unknown_shape(canvas, image_draw, layer):
    draw = image_draw.Draw(canvas, "RGBA")
    x, y, width, height = _box_values(layer)
    draw.rectangle(_box(x, y, width, height), outline=(255, 0, 255, 180), fill=(255, 0, 255, 45), width=2)
    draw.line((x, y, x + width, y + height), fill=(255, 0, 255, 180), width=1)
    draw.line((x + width, y, x, y + height), fill=(255, 0, 255, 180), width=1)


def _rgba(color, opacity):
    alpha = int(max(0, min(1, opacity)) * 255)
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


def _box_values(layer):
    return float(layer["x"]), float(layer["y"]), float(layer["width"]), float(layer["height"])


def _box(x, y, width, height):
    return (
        min(x, x + width),
        min(y, y + height),
        max(x, x + width),
        max(y, y + height),
    )


def _center(layer):
    return (layer["x"] + layer["width"] / 2, layer["y"] + layer["height"] / 2)
