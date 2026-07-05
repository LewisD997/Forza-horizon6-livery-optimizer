import csv
import json
from collections import Counter
from pathlib import Path


TYPE_COLORS = {
    "low_alpha_large_soft_shape": (255, 170, 0, 230),
    "tiny_fragment_cluster_member": (255, 80, 80, 230),
    "ellipse_cluster_member": (130, 95, 255, 230),
    "high_diff_overlap_member": (255, 40, 180, 230),
    "background_or_near_background_shape": (80, 200, 255, 230),
    "duplicate_like_shape": (80, 230, 120, 230),
    "unknown_review_candidate": (230, 230, 230, 230),
}

RISK_STYLES = {
    "low": {"width": 4, "fill": (0, 255, 120, 55)},
    "review_only": {"width": 2, "fill": (255, 230, 0, 45)},
}

FEEDBACK_COLORS = {
    "accepted": (0, 220, 120, 255),
    "rejected": (255, 70, 70, 255),
    "protected": (80, 170, 255, 255),
    "unsure": (255, 220, 70, 255),
}

FEEDBACK_FILLS = {
    "accepted": (0, 220, 120, 60),
    "rejected": (255, 70, 70, 65),
    "protected": (100, 120, 255, 65),
    "unsure": (255, 220, 70, 55),
}

FEEDBACK_STATUSES = ("accepted", "rejected", "protected", "unsure")
FEEDBACK_SORT_PRIORITY = {"protected": 0, "rejected": 1, "accepted": 2, "unsure": 3, "none": 4}


def render_candidate_overlay(
    base_image_path: str,
    plan: dict,
    geometry: dict,
    output_path: str,
    options: dict | None = None,
) -> dict:
    from PIL import Image, ImageDraw

    options = options or {}
    base = Image.open(base_image_path).convert("RGBA")
    draw = ImageDraw.Draw(base, "RGBA")
    candidates = _filtered_candidates(plan, options)
    transform = _coordinate_transform(base.size, geometry, options)
    rendered = 0
    skipped = 0

    for candidate in candidates:
        bbox = _candidate_bbox(candidate, transform)
        if not bbox:
            skipped += 1
            continue
        color = _candidate_color(candidate, options)
        risk = _risk(candidate)
        style = RISK_STYLES.get(risk, RISK_STYLES["review_only"])
        fill = _candidate_fill(candidate, options, style["fill"])
        width = max(style["width"], 4 if _feedback_status(candidate, options) != "none" else style["width"])
        draw.rectangle(bbox, fill=fill, outline=color, width=width)
        label = _overlay_label(candidate, options)
        if options.get("show_shape_index", True):
            label = f"{label} s{candidate.get('shape_index')}"
        _draw_label(draw, bbox, label, color)
        rendered += 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output)
    return {
        "output_path": str(output),
        "rendered_candidates": rendered,
        "skipped_candidates": skipped,
        "total_candidates": len(candidates),
    }


def render_candidate_contact_sheet(
    base_image_path: str,
    plan: dict,
    geometry: dict,
    output_path: str,
    options: dict | None = None,
) -> dict:
    from PIL import Image, ImageDraw

    options = options or {}
    top_n = int(options.get("top_n", 50))
    padding = int(options.get("crop_padding", 18))
    tile_width = int(options.get("tile_width", 260))
    tile_height = int(options.get("tile_height", 250))
    columns = int(options.get("columns", 5))
    base = Image.open(base_image_path).convert("RGBA")
    transform = _coordinate_transform(base.size, geometry, options)
    candidates = _sort_candidates(_filtered_candidates(plan, options), options)[:top_n]
    rows = max(1, (len(candidates) + columns - 1) // columns)
    sheet = Image.new("RGBA", (columns * tile_width, rows * tile_height), (32, 32, 32, 255))
    draw = ImageDraw.Draw(sheet, "RGBA")
    rendered = 0
    skipped = 0

    for index, candidate in enumerate(candidates):
        bbox = _candidate_bbox(candidate, transform)
        if not bbox:
            skipped += 1
            continue
        crop_box = _pad_box(bbox, padding, base.size)
        crop = base.crop(crop_box)
        crop.thumbnail((tile_width - 16, tile_height - 96))
        x = (index % columns) * tile_width
        y = (index // columns) * tile_height
        sheet.paste(crop, (x + 8, y + 8))
        color = _candidate_color(candidate, options)
        draw.rectangle((x, y, x + tile_width - 1, y + tile_height - 1), outline=color, width=2)
        lines = _candidate_text_lines(candidate, options)
        for line_index, line in enumerate(lines[:6]):
            draw.text((x + 8, y + tile_height - 86 + line_index * 14), line, fill=(245, 245, 245, 255))
        rendered += 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return {
        "output_path": str(output),
        "rendered_candidates": rendered,
        "skipped_candidates": skipped,
        "total_candidates": len(candidates),
    }


def export_candidate_crops(
    base_image_path: str,
    plan: dict,
    geometry: dict,
    output_dir: str,
    options: dict | None = None,
) -> dict:
    from PIL import Image, ImageDraw

    options = options or {}
    padding = int(options.get("crop_padding", 24))
    base = Image.open(base_image_path).convert("RGBA")
    transform = _coordinate_transform(base.size, geometry, options)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = []
    skipped = 0

    for candidate in _filtered_candidates(plan, options):
        bbox = _candidate_bbox(candidate, transform)
        if not bbox:
            skipped += 1
            continue
        crop_box = _pad_box(bbox, padding, base.size)
        crop = base.crop(crop_box)
        draw = ImageDraw.Draw(crop, "RGBA")
        local = (bbox[0] - crop_box[0], bbox[1] - crop_box[1], bbox[2] - crop_box[0], bbox[3] - crop_box[1])
        color = _candidate_color(candidate, options)
        draw.rectangle(local, outline=color, width=3)
        _draw_label(draw, local, _overlay_label(candidate, options), color)
        filename = _crop_filename(candidate)
        crop_file = output_path / filename
        crop.save(crop_file)
        paths.append(str(crop_file))

    return {
        "output_dir": str(output_path),
        "rendered_candidates": len(paths),
        "skipped_candidates": skipped,
        "crop_paths": paths,
    }


def write_candidate_review_index(plan, output_path, output_paths, warnings=None, feedback=None, feedback_path=None):
    candidates = _candidate_changes(plan)
    by_type = Counter(_candidate_type(change) for change in candidates)
    by_risk = Counter(_risk(change) for change in candidates)
    feedback_counts = _feedback_counts(feedback)
    reviewed_count = _reviewed_count(feedback)
    index = {
        "total_candidates": len(candidates),
        "rendered_candidates": output_paths.get("rendered_candidates"),
        "skipped_candidates": output_paths.get("skipped_candidates", 0),
        "counts_by_type": dict(sorted(by_type.items())),
        "counts_by_risk": dict(sorted(by_risk.items())),
        "output_paths": output_paths,
        "top_candidates": [_candidate_summary(change) for change in _top_candidates(candidates, 10)],
        "feedback_available": isinstance(feedback, dict),
        "feedback_path": str(feedback_path) if feedback_path else None,
        "feedback_counts": feedback_counts,
        "feedback_counts_by_status": feedback_counts,
        "outputs_by_feedback_status": output_paths.get("outputs_by_feedback_status", {}),
        "reviewed_count": reviewed_count,
        "unreviewed_count": max(0, len(candidates) - reviewed_count),
        "protected_count": feedback_counts.get("protected", 0),
        "accepted_count": feedback_counts.get("accepted", 0),
        "rejected_count": feedback_counts.get("rejected", 0),
        "unsure_count": feedback_counts.get("unsure", 0),
        "warnings": warnings or [],
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def write_review_summary(plan, output_path, feedback=None, warnings=None):
    candidates = _candidate_changes(plan)
    by_type = Counter(_candidate_type(change) for change in candidates)
    by_risk = Counter(_risk(change) for change in candidates)
    feedback_counts = _feedback_counts(feedback)
    lines = [
        "FLO Candidate Review Summary",
        "",
        f"Total candidates: {len(candidates)}",
        f"Type counts: {dict(sorted(by_type.items()))}",
        f"Risk counts: {dict(sorted(by_risk.items()))}",
    ]
    if isinstance(feedback, dict):
        lines.extend(
            [
                "",
                "Feedback summary:",
                f"Counts by status: {feedback_counts}",
                f"Accepted: {feedback_counts.get('accepted', 0)}",
                f"Rejected: {feedback_counts.get('rejected', 0)}",
                f"Protected: {feedback_counts.get('protected', 0)}",
                f"Unsure: {feedback_counts.get('unsure', 0)}",
            ]
        )
    if warnings:
        lines.extend(["", "Feedback warnings:"])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(["", "Top 10 candidates:"])
    feedback_by_id = _feedback_by_id(feedback)
    for candidate in _top_candidates(candidates, 10):
        summary = _candidate_summary(candidate)
        feedback_status = _feedback_status(candidate, {"feedback_by_id": feedback_by_id})
        lines.append(
            f"- {summary['change_id']} shape={summary['shape_index']} "
            f"type={summary['candidate_type']} score={summary['candidate_score']} "
            f"risk={summary['risk_level']} feedback={feedback_status}"
        )
    lines.extend(
        [
            "",
            "Human review instructions:",
            "- Candidates are not deleted.",
            "- Low risk does not mean automatically removable.",
            "- Accepted means candidate may be tested later.",
            "- Rejected means the candidate should not be removed.",
            "- Protected means future cleanup must not touch it.",
            "- Unsure means the candidate needs more review.",
            "- Review before cleanup.",
            "- This version does not modify geometry.",
        ]
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def write_candidate_review_csv(plan, output_path):
    rows = []
    for change in _candidate_changes(plan):
        metadata = change.get("metadata") or {}
        region = metadata.get("region") or {}
        rows.append(
            {
                "change_id": change.get("change_id"),
                "shape_index": change.get("shape_index"),
                "shape_uid": change.get("shape_uid"),
                "shape_type": change.get("shape_type"),
                "candidate_type": metadata.get("candidate_type"),
                "candidate_score": metadata.get("candidate_score"),
                "risk_level": change.get("risk_level"),
                "layer_alpha": metadata.get("layer_alpha"),
                "layer_area_estimate": metadata.get("layer_area_estimate"),
                "x": region.get("x"),
                "y": region.get("y"),
                "width": region.get("width"),
                "height": region.get("height"),
                "artifact_reasons": ";".join(metadata.get("artifact_reasons") or []),
            }
        )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else _csv_fields())
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def write_candidate_feedback_review_csv(plan, output_path, feedback=None):
    feedback_by_id = _feedback_by_id(feedback)
    rows = []
    for change in _candidate_changes(plan):
        metadata = change.get("metadata") or {}
        region = metadata.get("region") or {}
        item = feedback_by_id.get(change.get("change_id")) or {}
        rows.append(
            {
                "change_id": change.get("change_id"),
                "shape_index": change.get("shape_index"),
                "shape_uid": change.get("shape_uid"),
                "candidate_type": metadata.get("candidate_type"),
                "candidate_score": metadata.get("candidate_score"),
                "risk_level": change.get("risk_level"),
                "feedback_status": item.get("status", "none"),
                "reviewer_note": item.get("reviewer_note", ""),
                "reviewed_at": item.get("reviewed_at"),
                "x": region.get("x"),
                "y": region.get("y"),
                "width": region.get("width"),
                "height": region.get("height"),
                "artifact_reasons": ";".join(metadata.get("artifact_reasons") or []),
            }
        )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "change_id",
        "shape_index",
        "shape_uid",
        "candidate_type",
        "candidate_score",
        "risk_level",
        "feedback_status",
        "reviewer_note",
        "reviewed_at",
        "x",
        "y",
        "width",
        "height",
        "artifact_reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def build_feedback_review_warnings(plan, feedback):
    if not isinstance(feedback, dict):
        return []
    warnings = []
    candidates = _candidate_changes(plan)
    plan_by_id = {change.get("change_id"): change for change in candidates}
    feedback_by_id = _feedback_by_id(feedback)
    for change_id, item in sorted(feedback_by_id.items()):
        change = plan_by_id.get(change_id)
        if not change:
            warnings.append(f"Feedback item {change_id} does not exist in plan.")
            continue
        if item.get("shape_uid") != change.get("shape_uid"):
            warnings.append(f"Feedback item {change_id} shape_uid does not match plan.")
    for change in candidates:
        change_id = change.get("change_id")
        if change_id not in feedback_by_id:
            warnings.append(f"Plan candidate {change_id} has no feedback item.")
    return warnings


def _candidate_changes(plan):
    return [
        change
        for change in plan.get("changes", [])
        if change.get("action") == "mark_candidate" and isinstance(change.get("metadata"), dict)
    ]


def _filtered_candidates(plan, options):
    candidates = _candidate_changes(plan)
    candidate_type = options.get("candidate_type")
    risk_level = options.get("risk_level")
    feedback_status = options.get("feedback_status")
    if candidate_type:
        candidates = [change for change in candidates if _candidate_type(change) == candidate_type]
    if risk_level:
        candidates = [change for change in candidates if _risk(change) == risk_level]
    if feedback_status:
        candidates = [change for change in candidates if _feedback_status(change, options) == feedback_status]
    return candidates


def _sort_candidates(candidates, options):
    if options.get("group_feedback_first"):
        return sorted(
            candidates,
            key=lambda change: (
                FEEDBACK_SORT_PRIORITY.get(_feedback_status(change, options), 9),
                -_candidate_score(change),
            ),
        )
    return sorted(candidates, key=lambda change: _candidate_score(change), reverse=True)


def _top_candidates(candidates, count):
    return sorted(candidates, key=lambda change: _candidate_score(change), reverse=True)[:count]


def _candidate_score(change):
    try:
        return float((change.get("metadata") or {}).get("candidate_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _candidate_type(change):
    return (change.get("metadata") or {}).get("candidate_type") or "unknown_review_candidate"


def _risk(change):
    return change.get("risk_level") or "review_only"


def _candidate_summary(change):
    metadata = change.get("metadata") or {}
    return {
        "change_id": change.get("change_id"),
        "shape_index": change.get("shape_index"),
        "shape_uid": change.get("shape_uid"),
        "candidate_type": metadata.get("candidate_type"),
        "candidate_score": metadata.get("candidate_score"),
        "risk_level": change.get("risk_level"),
        "region": metadata.get("region"),
        "artifact_reasons": metadata.get("artifact_reasons") or [],
    }


def _candidate_bbox(candidate, transform):
    region = (candidate.get("metadata") or {}).get("region")
    if not isinstance(region, dict):
        return None
    x = _number(region.get("x"))
    y = _number(region.get("y"))
    width = _number(region.get("width"))
    height = _number(region.get("height"))
    if width <= 0 or height <= 0:
        return None
    x0 = int(round((x + transform["offset_x"]) * transform["scale_x"]))
    y0 = int(round((y + transform["offset_y"]) * transform["scale_y"]))
    x1 = int(round((x + width + transform["offset_x"]) * transform["scale_x"]))
    y1 = int(round((y + height + transform["offset_y"]) * transform["scale_y"]))
    return (min(x0, x1), min(y0, y1), max(x0 + 1, x1), max(y0 + 1, y1))


def _coordinate_transform(base_size, geometry, options):
    canvas_width, canvas_height = _geometry_canvas_size(geometry)
    return {
        "scale_x": base_size[0] / canvas_width if canvas_width else 1.0,
        "scale_y": base_size[1] / canvas_height if canvas_height else 1.0,
        "offset_x": float(options.get("offset_x", 0)),
        "offset_y": float(options.get("offset_y", 0)),
    }


def _geometry_canvas_size(geometry):
    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else []
    if shapes:
        data = shapes[0].get("data") if isinstance(shapes[0], dict) else None
        if isinstance(data, list) and len(data) >= 4:
            return max(1.0, abs(_number(data[2]))), max(1.0, abs(_number(data[3])))
    return 1000.0, 1000.0


def _draw_label(draw, bbox, text, color):
    x0, y0, x1, _ = bbox
    label_box = (x0, max(0, y0 - 16), min(x1 + 80, x0 + 100), y0)
    draw.rectangle(label_box, fill=(0, 0, 0, 190))
    draw.text((label_box[0] + 3, label_box[1] + 2), str(text), fill=color)


def _candidate_text_lines(candidate, options=None):
    options = options or {}
    metadata = candidate.get("metadata") or {}
    feedback_status = _feedback_status(candidate, options)
    note = _feedback_note(candidate, options)
    return [
        f"{candidate.get('change_id')} shape {candidate.get('shape_index')}",
        str(metadata.get("candidate_type")),
        f"score {metadata.get('candidate_score')} risk {candidate.get('risk_level')}",
        f"feedback {feedback_status}",
        f"alpha {metadata.get('layer_alpha')}",
        f"note {_note_preview(note)}" if note else "note",
    ]


def _pad_box(bbox, padding, image_size):
    return (
        max(0, bbox[0] - padding),
        max(0, bbox[1] - padding),
        min(image_size[0], bbox[2] + padding),
        min(image_size[1], bbox[3] + padding),
    )


def _crop_filename(candidate):
    return (
        f"{candidate.get('change_id')}_shape_{candidate.get('shape_index')}_"
        f"{_candidate_type(candidate)}.png"
    )


def _candidate_color(candidate, options):
    status = _feedback_status(candidate, options)
    if status in FEEDBACK_COLORS:
        return FEEDBACK_COLORS[status]
    return TYPE_COLORS.get(_candidate_type(candidate), TYPE_COLORS["unknown_review_candidate"])


def _candidate_fill(candidate, options, fallback):
    status = _feedback_status(candidate, options)
    return FEEDBACK_FILLS.get(status, fallback)


def _overlay_label(candidate, options):
    status = _feedback_status(candidate, options)
    if status != "none":
        return f"{candidate.get('change_id', '?')} {status}"
    return candidate.get("change_id", "?")


def _feedback_status(candidate, options):
    item = _feedback_item(candidate, options)
    return item.get("status", "none")


def _feedback_note(candidate, options):
    item = _feedback_item(candidate, options)
    return item.get("reviewer_note") or ""


def _feedback_item(candidate, options):
    feedback_by_id = options.get("feedback_by_id") or {}
    item = feedback_by_id.get(candidate.get("change_id")) or {}
    return item if isinstance(item, dict) else {}


def _feedback_by_id(feedback):
    if not isinstance(feedback, dict):
        return {}
    return {item.get("change_id"): item for item in feedback.get("items", []) if item.get("change_id")}


def _feedback_counts(feedback):
    if not isinstance(feedback, dict):
        return {}
    counts = feedback.get("counts_by_status") or {}
    return {status: int(counts.get(status, 0) or 0) for status in FEEDBACK_STATUSES}


def _reviewed_count(feedback):
    if not isinstance(feedback, dict):
        return 0
    count = 0
    for item in feedback.get("items", []):
        if item.get("status") != "unsure" or item.get("reviewed_at"):
            count += 1
    return count


def _note_preview(note, limit=42):
    text = " ".join(str(note).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _csv_fields():
    return [
        "change_id",
        "shape_index",
        "shape_uid",
        "shape_type",
        "candidate_type",
        "candidate_score",
        "risk_level",
        "layer_alpha",
        "layer_area_estimate",
        "x",
        "y",
        "width",
        "height",
        "artifact_reasons",
    ]


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
