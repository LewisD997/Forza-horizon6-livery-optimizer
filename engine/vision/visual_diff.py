from pathlib import Path


class VisualDiffError(Exception):
    pass


def compare_images(original_path, preview_path, diff_path):
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise VisualDiffError("Please install Pillow with: pip install pillow") from exc

    original = Image.open(original_path).convert("RGB")
    preview = _open_preview(preview_path, original.size, Image)

    diff = ImageChops.difference(original, preview)
    global_score = _global_difference_score(diff)
    high_difference_regions = _high_difference_regions(diff)

    output_path = Path(diff_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _make_visible_diff(diff).save(output_path)

    return {
        "diff_path": str(output_path),
        "global_difference_score": global_score,
        "high_difference_regions": high_difference_regions,
    }


def _open_preview(path, size, image_module):
    preview = image_module.open(path).convert("RGBA")
    if preview.size != size:
        preview = preview.resize(size, image_module.Resampling.BICUBIC)

    background = image_module.new("RGBA", size, (255, 255, 255, 255))
    background.alpha_composite(preview)
    return background.convert("RGB")


def _global_difference_score(diff):
    pixels = list(diff.getdata())
    if not pixels:
        return 0.0

    total = sum((r + g + b) / (255 * 3) for r, g, b in pixels)
    return round(total / len(pixels), 4)


def _high_difference_regions(diff, grid_size=40):
    width, height = diff.size
    regions = []

    for y in range(0, height, grid_size):
        for x in range(0, width, grid_size):
            box = (x, y, min(x + grid_size, width), min(y + grid_size, height))
            tile = diff.crop(box)
            score = _global_difference_score(tile)
            if score >= 0.18:
                regions.append(
                    {
                        "x": box[0],
                        "y": box[1],
                        "width": box[2] - box[0],
                        "height": box[3] - box[1],
                        "difference_score": score,
                    }
                )

    regions.sort(key=lambda region: region["difference_score"], reverse=True)
    return regions[:16]


def _make_visible_diff(diff):
    # Boost the contrast so small mismatches are visible when opened by a human.
    return diff.point(lambda value: min(255, value * 3))
