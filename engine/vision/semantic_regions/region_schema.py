SEMANTIC_REGION_VERSION = "0.7.0"
VALID_LABELS = (
    "background", "hair", "face_skin", "eyes", "mouth", "body_skin",
    "clothing", "outline_edge", "foreground_unknown", "unknown",
)
EXCLUSIVE_LABELS = tuple(label for label in VALID_LABELS if label not in {"outline_edge", "unknown"})
SENSITIVE_LABELS = {"eyes", "face_skin", "mouth", "outline_edge"}
REGION_IDS = {label: index for index, label in enumerate(VALID_LABELS)}
PALETTE = {
    "background": (28, 32, 38), "hair": (220, 70, 90), "face_skin": (255, 190, 145),
    "eyes": (45, 210, 235), "mouth": (210, 45, 95), "body_skin": (245, 160, 120),
    "clothing": (65, 110, 220), "outline_edge": (255, 225, 45),
    "foreground_unknown": (150, 150, 160), "unknown": (0, 0, 0),
}


def confidence_level(value):
    value = validate_confidence(value)
    if value >= 0.75: return "high"
    if value >= 0.45: return "medium"
    return "low"


def validate_confidence(value):
    value = float(value)
    if not 0.0 <= value <= 1.0: raise ValueError("Confidence must be in [0, 1].")
    return value


def make_region_record(label, confidence, bbox, area, foreground_count, backend, evidence=None, warnings=None, mask_path=None):
    if label not in VALID_LABELS: raise ValueError(f"Invalid semantic label: {label}")
    confidence = validate_confidence(confidence)
    return {
        "region_id": f"region_{label}_001", "label": label, "parent_label": None,
        "confidence": round(confidence, 4), "confidence_level": confidence_level(confidence),
        "bbox": bbox, "pixel_area": int(area),
        "foreground_area_ratio": round(area / max(1, foreground_count), 6),
        "source_backend": backend, "evidence": evidence or [], "warnings": warnings or [], "mask_path": mask_path,
    }
