import json
import shutil
from pathlib import Path

from engine.optimizer.ablation_auto_triage import TRIAGE_VERSION, VALID_TRIAGE_DECISIONS, triage_ablation_result


EVIDENCE_PACK_VERSION = "0.6.10"


def generate_ablation_evidence_pack(
    ablation_report: dict,
    output_dir: str,
    options: dict | None = None,
) -> dict:
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont
    except ImportError as exc:
        raise RuntimeError("Please install Pillow with: pip install pillow") from exc

    options = options or {}
    output = Path(output_dir)
    overwrite = bool(options.get("overwrite", False))
    candidate_filter = options.get("candidate_id")
    max_candidates = options.get("max_candidates")
    output.mkdir(parents=True, exist_ok=True)

    results = ablation_report.get("results", [])
    if candidate_filter:
        results = [item for item in results if item.get("change_id") == candidate_filter]
    if max_candidates is not None:
        results = results[: max(0, int(max_candidates))]

    warnings = []
    candidates = []
    cards = []
    for result in results:
        try:
            evidence = _candidate_evidence(result, output, options, overwrite, Image, ImageChops, ImageDraw, ImageEnhance, ImageFont)
            candidates.append(evidence["report_entry"])
            cards.append(evidence["card_path"])
            warnings.extend(evidence.get("warnings", []))
        except Exception as exc:
            warnings.append(f"Evidence failed for {result.get('change_id')}: {exc}")
            candidates.append(_failed_entry(result, str(exc)))

    combined_sheet = str(output / "ablation_evidence_sheet.png")
    if cards:
        _write_combined_sheet(cards, combined_sheet, overwrite, Image, ImageDraw, ImageFont)
    assistant_pack = _write_assistant_review_pack(output, candidates, combined_sheet if cards else None, overwrite, Image)
    report = {
        "evidence_pack_version": EVIDENCE_PACK_VERSION,
        "status": _status(results, warnings),
        "source_ablation_report": _path_string(options.get("source_ablation_report")),
        "candidate_count": len(results),
        "triage_counts": _triage_counts(candidates),
        "candidates": candidates,
        "assistant_review_pack": assistant_pack,
        "safety": {
            "original_geometry_modified": False,
            "original_feedback_modified": False,
            "official_cleanup_output_written": False,
            "evidence_only": True,
        },
        "warnings": warnings,
    }
    _write_json(report, output / "ablation_evidence_pack_report.json", overwrite)
    return report


def _candidate_evidence(result, output, options, overwrite, Image, ImageChops, ImageDraw, ImageEnhance, ImageFont):
    change_id = result.get("change_id") or "unknown"
    candidate_dir = output / "candidates" / _safe_name(change_id)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    paths = result.get("outputs") or {}
    before_path = Path(paths.get("before_preview") or "")
    after_path = Path(paths.get("after_preview") or "")
    diff_path = Path(paths.get("diff") or "")
    impact_path = Path(paths.get("impact_report") or "")
    if not before_path.exists() or not after_path.exists():
        warnings.append(f"{change_id}: before or after preview missing.")
        raise FileNotFoundError("before_preview or after_preview missing")

    before = Image.open(before_path).convert("RGBA")
    after = Image.open(after_path).convert("RGBA")
    diff = _load_or_make_diff(diff_path, before, after, Image, ImageChops)
    impact_report = _load_json(impact_path) if impact_path.exists() else {}
    region = _candidate_region(result, impact_report)
    changed_bbox = _changed_bbox(impact_report)
    crop_box = _crop_box(before.size, region, changed_bbox, int(options.get("crop_padding", 32)))
    scale = max(1, int(options.get("upscale", 4)))
    amplify = float(options.get("amplify_diff", 6.0))

    before_crop = _crop_upscale(before, crop_box, scale, Image)
    after_crop = _crop_upscale(after, crop_box, scale, Image)
    diff_crop = _crop_upscale(diff, crop_box, scale, Image)
    amplified = ImageEnhance.Contrast(diff_crop).enhance(amplify)
    amplified = amplified.point(lambda value: min(255, int(value * amplify)))

    local_region = _local_box(region, crop_box, scale)
    local_changed = _local_box(changed_bbox, crop_box, scale)
    for image in (before_crop, after_crop, diff_crop, amplified):
        _draw_boxes(image, local_region, local_changed, ImageDraw)

    overlay = before_crop.copy()
    _draw_overlay(overlay, local_region, local_changed, ImageDraw)
    side_by_side = _side_by_side([before_crop, after_crop], ["before", "after"], Image, ImageDraw, ImageFont)
    card = _review_card(result, before_crop, after_crop, amplified, region, changed_bbox, Image, ImageDraw, ImageFont)
    overview = before.copy()
    _draw_full_overview(overview, crop_box, region, changed_bbox, ImageDraw)

    outputs = {
        "before_crop": str(candidate_dir / "before_crop.png"),
        "after_crop": str(candidate_dir / "after_crop.png"),
        "diff_crop": str(candidate_dir / "diff_crop.png"),
        "amplified_diff_crop": str(candidate_dir / "amplified_diff_crop.png"),
        "candidate_mask_overlay": str(candidate_dir / "candidate_mask_overlay.png"),
        "before_after_side_by_side": str(candidate_dir / "before_after_side_by_side.png"),
        "review_card": str(candidate_dir / "before_after_diff_card.png"),
        "candidate_location_overview": str(candidate_dir / "candidate_location_overview.png"),
        "metadata": str(candidate_dir / "evidence_metadata.json"),
    }
    _save(before_crop, outputs["before_crop"], overwrite)
    _save(after_crop, outputs["after_crop"], overwrite)
    _save(diff_crop, outputs["diff_crop"], overwrite)
    _save(amplified, outputs["amplified_diff_crop"], overwrite)
    _save(overlay, outputs["candidate_mask_overlay"], overwrite)
    _save(side_by_side, outputs["before_after_side_by_side"], overwrite)
    _save(card, outputs["review_card"], overwrite)
    _save(overview, outputs["candidate_location_overview"], overwrite)

    triage = triage_ablation_result(result)
    metadata = {
        "change_id": change_id,
        "crop_box": _box_dict(crop_box),
        "candidate_region": region,
        "changed_bbox": changed_bbox,
        "upscale": scale,
        "amplify_diff": amplify,
        "triage": triage,
    }
    _write_json(metadata, outputs["metadata"], overwrite)
    entry = {
        "change_id": change_id,
        "shape_index": result.get("shape_index"),
        "candidate_type": result.get("candidate_type"),
        "impact_decision": (result.get("impact") or {}).get("overall_decision"),
        "global_changed_pixel_ratio": (result.get("impact") or {}).get("changed_pixel_ratio"),
        "local_changed_pixel_ratio": (result.get("impact") or {}).get("local_changed_pixel_ratio"),
        "mean_abs_diff": (result.get("impact") or {}).get("mean_abs_diff"),
        "triage_decision": triage["triage_decision"],
        "triage_confidence": triage["triage_confidence"],
        "triage_reasons": triage["triage_reasons"],
        "recommended_next_action": triage["recommended_next_action"],
        "outputs": outputs,
    }
    return {"report_entry": entry, "card_path": outputs["review_card"], "warnings": warnings}


def _review_card(result, before_crop, after_crop, amplified, region, changed_bbox, Image, ImageDraw, ImageFont):
    font = ImageFont.load_default()
    width = max(960, before_crop.width + after_crop.width + amplified.width + 80)
    image_row_height = max(before_crop.height, after_crop.height, amplified.height)
    height = image_row_height + 180
    card = Image.new("RGBA", (width, height), (248, 248, 248, 255))
    draw = ImageDraw.Draw(card)
    triage = triage_ablation_result(result)
    impact = result.get("impact") or {}
    lines = [
        f"change_id: {result.get('change_id')}    shape_index: {result.get('shape_index')}",
        f"type: {result.get('candidate_type')}    risk: {result.get('risk_level')}    impact: {impact.get('overall_decision')}",
        f"global: {impact.get('changed_pixel_ratio')}    local: {impact.get('local_changed_pixel_ratio')}    mean: {impact.get('mean_abs_diff')}",
        f"triage: {triage['triage_decision']} ({triage['triage_confidence']})",
        f"reason: {'; '.join(triage['triage_reasons'])}",
    ]
    y = 10
    for line in lines:
        draw.text((12, y), line, fill=(20, 20, 20, 255), font=font)
        y += 18
    labels = [("before crop", before_crop), ("after crop", after_crop), ("amplified diff", amplified)]
    x = 12
    y = 120
    for label, tile in labels:
        draw.text((x, y - 18), label, fill=(0, 0, 0, 255), font=font)
        card.alpha_composite(tile, (x, y))
        x += tile.width + 24
    return card


def _side_by_side(images, labels, Image, ImageDraw, ImageFont):
    font = ImageFont.load_default()
    width = sum(image.width for image in images) + 24 * (len(images) + 1)
    height = max(image.height for image in images) + 46
    sheet = Image.new("RGBA", (width, height), (245, 245, 245, 255))
    draw = ImageDraw.Draw(sheet)
    x = 24
    for label, image in zip(labels, images):
        draw.text((x, 10), label, fill=(0, 0, 0, 255), font=font)
        sheet.alpha_composite(image, (x, 32))
        x += image.width + 24
    return sheet


def _write_combined_sheet(cards, path, overwrite, Image, ImageDraw, ImageFont):
    card_images = [Image.open(card).convert("RGBA") for card in cards]
    width = max(image.width for image in card_images)
    height = sum(image.height for image in card_images) + 12 * (len(card_images) + 1)
    sheet = Image.new("RGBA", (width, height), (238, 238, 238, 255))
    y = 12
    for image in card_images:
        sheet.alpha_composite(image, (0, y))
        y += image.height + 12
    _save(sheet, path, overwrite)


def _write_assistant_review_pack(output, candidates, combined_sheet, overwrite, Image):
    pack = output / "assistant_review_pack"
    pack.mkdir(parents=True, exist_ok=True)
    manifest_path = pack / "assistant_review_manifest.json"
    sheet_path = pack / "assistant_review_sheet.png"
    summary_path = pack / "assistant_review_summary.txt"
    if combined_sheet and Path(combined_sheet).exists():
        if sheet_path.exists() and not overwrite:
            raise FileExistsError(f"Output already exists: {sheet_path}")
        shutil.copyfile(combined_sheet, sheet_path)
    recommended = [candidate["outputs"]["review_card"] for candidate in candidates if "review_card" in candidate.get("outputs", {})]
    manifest = {
        "assistant_review_pack_version": EVIDENCE_PACK_VERSION,
        "candidate_ids": [candidate.get("change_id") for candidate in candidates],
        "triage_decisions": {candidate.get("change_id"): candidate.get("triage_decision") for candidate in candidates},
        "metric_summary": [
            {
                "change_id": candidate.get("change_id"),
                "global_changed_pixel_ratio": candidate.get("global_changed_pixel_ratio"),
                "local_changed_pixel_ratio": candidate.get("local_changed_pixel_ratio"),
                "triage_decision": candidate.get("triage_decision"),
            }
            for candidate in candidates
        ],
        "review_cards": recommended,
        "suggested_files_to_send_to_chatgpt": [str(sheet_path)] + recommended,
    }
    _write_json(manifest, manifest_path, overwrite)
    lines = [
        "Please review whether these should be deleted, protected, or treated as replacement candidates.",
        "",
        "Candidates:",
    ]
    for candidate in candidates:
        lines.append(
            "- {id}: triage={triage}, global={global_ratio}, local={local_ratio}, type={candidate_type}".format(
                id=candidate.get("change_id"),
                triage=candidate.get("triage_decision"),
                global_ratio=candidate.get("global_changed_pixel_ratio"),
                local_ratio=candidate.get("local_changed_pixel_ratio"),
                candidate_type=candidate.get("candidate_type"),
            )
        )
    _write_text(summary_path, "\n".join(lines), overwrite)
    return {
        "manifest": str(manifest_path),
        "combined_sheet": str(sheet_path) if sheet_path.exists() else None,
        "summary": str(summary_path),
        "recommended_files_to_upload": manifest["suggested_files_to_send_to_chatgpt"],
    }


def _load_or_make_diff(diff_path, before, after, Image, ImageChops):
    if diff_path.exists():
        return Image.open(diff_path).convert("RGBA")
    return ImageChops.difference(before.convert("RGB"), after.convert("RGB")).convert("RGBA")


def _candidate_region(result, impact_report):
    per_shape = impact_report.get("per_removed_shape_metrics") or []
    if per_shape and isinstance(per_shape[0].get("region"), dict):
        return per_shape[0]["region"]
    removed = ((impact_report.get("removal_report") or {}).get("removed_shapes") or [])
    if removed and isinstance(removed[0].get("region"), dict):
        return removed[0]["region"]
    return None


def _changed_bbox(impact_report):
    bbox = (impact_report.get("global_metrics") or {}).get("changed_bbox")
    return bbox if isinstance(bbox, dict) else None


def _crop_box(size, region, changed_bbox, padding):
    width, height = size
    boxes = [_dict_to_box(region), _dict_to_box(changed_bbox)]
    boxes = [box for box in boxes if box]
    if not boxes:
        return (0, 0, width, height)
    x0 = max(0, min(box[0] for box in boxes) - padding)
    y0 = max(0, min(box[1] for box in boxes) - padding)
    x1 = min(width, max(box[2] for box in boxes) + padding)
    y1 = min(height, max(box[3] for box in boxes) + padding)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, width, height)
    return (int(x0), int(y0), int(x1), int(y1))


def _dict_to_box(region):
    if not isinstance(region, dict):
        return None
    x = _number(region.get("x"))
    y = _number(region.get("y"))
    w = _number(region.get("width"))
    h = _number(region.get("height"))
    if w <= 0 or h <= 0:
        return None
    return (x, y, x + w, y + h)


def _local_box(region, crop_box, scale):
    box = _dict_to_box(region)
    if not box:
        return None
    x0, y0, x1, y1 = box
    cx0, cy0, _, _ = crop_box
    return (
        int((x0 - cx0) * scale),
        int((y0 - cy0) * scale),
        int((x1 - cx0) * scale),
        int((y1 - cy0) * scale),
    )


def _crop_upscale(image, crop_box, scale, Image):
    crop = image.crop(crop_box)
    if scale <= 1:
        return crop
    return crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.NEAREST)


def _draw_boxes(image, candidate_box, changed_box, ImageDraw):
    draw = ImageDraw.Draw(image)
    if candidate_box:
        draw.rectangle(candidate_box, outline=(0, 128, 255, 255), width=2)
        draw.text((candidate_box[0] + 4, max(0, candidate_box[1] - 14)), "candidate", fill=(0, 80, 180, 255))
    if changed_box:
        draw.rectangle(changed_box, outline=(255, 64, 0, 255), width=2)
        draw.text((changed_box[0] + 4, max(0, changed_box[1] - 28)), "changed", fill=(200, 40, 0, 255))


def _draw_overlay(image, candidate_box, changed_box, ImageDraw):
    overlay = ImageDraw.Draw(image, "RGBA")
    if candidate_box:
        overlay.rectangle(candidate_box, fill=(0, 128, 255, 60), outline=(0, 128, 255, 255), width=2)
    if changed_box:
        overlay.rectangle(changed_box, fill=(255, 64, 0, 60), outline=(255, 64, 0, 255), width=2)


def _draw_full_overview(image, crop_box, region, changed_bbox, ImageDraw):
    draw = ImageDraw.Draw(image)
    draw.rectangle(crop_box, outline=(255, 210, 0, 255), width=3)
    candidate = _dict_to_box(region)
    changed = _dict_to_box(changed_bbox)
    if candidate:
        draw.rectangle(candidate, outline=(0, 128, 255, 255), width=2)
    if changed:
        draw.rectangle(changed, outline=(255, 64, 0, 255), width=2)


def _failed_entry(result, reason):
    triage = {
        "triage_decision": "unclear_needs_review",
        "triage_confidence": 0.0,
        "triage_reasons": [reason],
        "recommended_next_action": "Regenerate evidence for this candidate.",
    }
    return {
        "change_id": result.get("change_id"),
        "shape_index": result.get("shape_index"),
        "candidate_type": result.get("candidate_type"),
        "impact_decision": (result.get("impact") or {}).get("overall_decision"),
        "global_changed_pixel_ratio": (result.get("impact") or {}).get("changed_pixel_ratio"),
        "local_changed_pixel_ratio": (result.get("impact") or {}).get("local_changed_pixel_ratio"),
        "mean_abs_diff": (result.get("impact") or {}).get("mean_abs_diff"),
        **triage,
        "outputs": {},
    }


def _status(results, warnings):
    if not results:
        return "no_candidates"
    if warnings:
        return "completed_with_warnings"
    return "completed"


def _triage_counts(candidates):
    counts = {decision: 0 for decision in VALID_TRIAGE_DECISIONS}
    for candidate in candidates:
        decision = candidate.get("triage_decision")
        if decision in counts:
            counts[decision] += 1
    return counts


def _save(image, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _write_json(data, path, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path, text, overwrite):
    output = Path(path)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _box_dict(box):
    if not box:
        return None
    x0, y0, x1, y1 = box
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0, "right": x1, "bottom": y1}


def _safe_name(value):
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value))


def _path_string(path):
    return str(path) if path else None


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
