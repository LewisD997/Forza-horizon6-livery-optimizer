from pathlib import Path


def get_alpha_bbox(image, threshold=1):
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    mask = alpha.point(lambda value: 255 if value >= threshold else 0)
    return mask.getbbox()


def crop_to_bbox(image, bbox, padding=0):
    if bbox is None:
        return image.copy()
    left, top, right, bottom = bbox
    width, height = image.size
    padded = (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )
    return image.crop(padded)


def compare_image_sizes(candidate, target):
    return {
        "candidate_size": {"width": candidate.size[0], "height": candidate.size[1]},
        "target_size": {"width": target.size[0], "height": target.size[1]},
        "dimensions_match": candidate.size == target.size,
    }


def align_candidate_to_target(candidate, target, mode="resize"):
    from PIL import Image

    if candidate.size == target.size:
        return candidate.copy(), {"mode": "none", "resized": False}
    if mode != "resize":
        raise ValueError("Only align mode 'resize' is supported.")
    return (
        candidate.resize(target.size, Image.Resampling.BICUBIC),
        {"mode": mode, "resized": True},
    )


def compare_images(candidate_path, target_path, diff_dir=None, prefix="diff", make_side_by_side=False):
    from PIL import Image, ImageChops

    candidate_path = Path(candidate_path)
    target_path = Path(target_path)
    if not target_path.exists():
        return {
            "available": False,
            "target_path": str(target_path),
            "difference_score": None,
            "resized_for_score": False,
            "diff_outputs": {},
        }

    with Image.open(candidate_path) as candidate_image:
        candidate = candidate_image.convert("RGBA")
    with Image.open(target_path) as target_image:
        target = target_image.convert("RGBA")

    original_candidate_size = candidate.size
    size_info = compare_image_sizes(candidate, target)
    aligned_candidate, alignment = align_candidate_to_target(candidate, target)
    diff_rgb = ImageChops.difference(target.convert("RGB"), aligned_candidate.convert("RGB"))
    score = _difference_score(diff_rgb)

    diff_outputs = {}
    if diff_dir:
        diff_outputs = write_diff_images(
            aligned_candidate,
            target,
            diff_dir,
            prefix=prefix,
            make_side_by_side=make_side_by_side,
        )

    return {
        "available": True,
        "target_path": str(target_path),
        "candidate_path": str(candidate_path),
        "target_size": size_info["target_size"],
        "candidate_size": {
            "width": original_candidate_size[0],
            "height": original_candidate_size[1],
        },
        "dimensions_match": size_info["dimensions_match"],
        "difference_score": score,
        "resized_for_score": alignment["resized"],
        "alignment": alignment,
        "diff_outputs": diff_outputs,
    }


def write_diff_images(candidate, target, output_dir, prefix="diff", make_side_by_side=False):
    from PIL import Image, ImageChops

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    candidate_rgba = candidate.convert("RGBA")
    target_rgba = target.convert("RGBA")
    candidate_rgb = candidate_rgba.convert("RGB")
    target_rgb = target_rgba.convert("RGB")
    residual = ImageChops.difference(target_rgb, candidate_rgb)
    grayscale = _abs_grayscale(residual)
    heatmap = _heatmap(grayscale)
    alpha_diff = ImageChops.difference(
        target_rgba.getchannel("A"),
        candidate_rgba.getchannel("A"),
    )
    overlay = Image.blend(target_rgba, candidate_rgba, 0.5)

    outputs = {
        "rgb_residual": str(output_path / f"{prefix}_rgb_residual.png"),
        "abs_grayscale": str(output_path / f"{prefix}_abs_grayscale.png"),
        "heatmap": str(output_path / f"{prefix}_heatmap.png"),
        "alpha": str(output_path / f"{prefix}_alpha.png"),
        "overlay": str(output_path / f"{prefix}_overlay.png"),
    }
    residual.save(outputs["rgb_residual"])
    grayscale.save(outputs["abs_grayscale"])
    heatmap.save(outputs["heatmap"])
    alpha_diff.save(outputs["alpha"])
    overlay.save(outputs["overlay"])

    if make_side_by_side:
        side_by_side = Image.new("RGBA", (target_rgba.width * 2, target_rgba.height), (0, 0, 0, 0))
        side_by_side.paste(target_rgba, (0, 0))
        side_by_side.paste(candidate_rgba, (target_rgba.width, 0))
        outputs["side_by_side"] = str(output_path / f"{prefix}_side_by_side.png")
        side_by_side.save(outputs["side_by_side"])

    return outputs


def _abs_grayscale(residual):
    import numpy as np
    from PIL import Image

    values = np.asarray(residual.convert("RGB"), dtype=np.float32)
    mean = np.rint(values.mean(axis=2)).clip(0, 255).astype("uint8")
    return Image.fromarray(mean, "L")


def _heatmap(grayscale):
    import numpy as np
    from PIL import Image

    values = np.asarray(grayscale, dtype=np.float32) / 255.0
    rgb = np.zeros((grayscale.height, grayscale.width, 3), dtype=np.uint8)
    rgb[:, :, 0] = np.clip((values * 2 - 0.5) * 255, 0, 255).astype("uint8")
    rgb[:, :, 1] = np.clip((1.0 - abs(values - 0.65) * 2.2) * 255, 0, 255).astype("uint8")
    rgb[:, :, 2] = np.clip((0.6 - values) * 255, 0, 180).astype("uint8")
    return Image.fromarray(rgb, "RGB")


def _difference_score(diff_rgb):
    pixel_count = diff_rgb.size[0] * diff_rgb.size[1]
    if pixel_count <= 0:
        return 0.0
    total = sum(diff_rgb.tobytes()) / (255 * 3)
    return round(total / pixel_count, 4)
