from pathlib import Path

from engine.vision.png_reader import inspect_png_with_stdlib


def inspect_reference_image(path):
    image_path = Path(path)
    if not image_path.exists():
        raise FileNotFoundError(f"Reference image not found: {image_path}")

    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return inspect_png_with_stdlib(image_path)

    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        dominant_colors = _dominant_colors(rgb)
        edge_density = _edge_density(rgb, ImageFilter)

    return {
        "path": str(image_path),
        "size": {"width": width, "height": height},
        "dominant_colors": dominant_colors,
        "edge_density": edge_density,
        "high_detail_regions": [],
    }


def _dominant_colors(image, count=5):
    sampled = image.copy()
    sampled.thumbnail((128, 128))
    quantized = sampled.quantize(colors=count)
    palette = quantized.getpalette()
    colors = quantized.getcolors()
    if not colors or not palette:
        return []

    result = []
    for pixel_count, palette_index in sorted(colors, reverse=True):
        offset = palette_index * 3
        rgb = palette[offset : offset + 3]
        result.append(
            {
                "color": f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}",
                "pixels": pixel_count,
            }
        )
    return result


def _edge_density(image, image_filter):
    grayscale = image.convert("L")
    edges = grayscale.filter(image_filter.FIND_EDGES)
    sampled = edges.resize((128, 128))
    values = list(sampled.getdata())
    if not values:
        return 0.0

    active_edges = sum(1 for value in values if value > 32)
    return round(active_edges / len(values), 4)
