import json
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_PATH = "database/forza_primitives.json"


@lru_cache(maxsize=1)
def load_primitive_kb(path=DEFAULT_KB_PATH):
    kb_path = Path(path)
    if not kb_path.is_absolute():
        kb_path = PROJECT_ROOT / kb_path
    data = json.loads(kb_path.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in data.get("primitives", [])}


def get_primitive_info(shape_id):
    kb = load_primitive_kb()
    normalized_id = _normalize_shape_id(shape_id)
    return kb.get(normalized_id, kb["unknown"])


def is_known_primitive(shape_id):
    kb = load_primitive_kb()
    return _normalize_shape_id(shape_id) in kb


def suggest_replacements(shape_id, problem_type):
    primitive = get_primitive_info(shape_id)
    candidates = primitive.get("replacement_candidates", {})
    normalized_problem = _normalize_problem_type(problem_type)
    if problem_type in candidates:
        return candidates[problem_type]
    if normalized_problem in candidates:
        return candidates[normalized_problem]
    if problem_type == "duplicate_layer":
        return []
    if problem_type == "nearly_identical_colors":
        return candidates.get("nearly_identical_colors", ["polygon"])
    if problem_type == "very_small_layer":
        return candidates.get("tiny_invisible_detail", candidates.get("very_small_layer", ["polygon"]))
    if problem_type == "edge_fixing_fragment":
        return candidates.get("edge_fixing_fragment", ["line", "arc"])
    if problem_type == "extremely_stretched_layer":
        return candidates.get("extreme_stretch", candidates.get("extremely_stretched_layer", ["line"]))
    return candidates.get(problem_type, candidates.get(normalized_problem, []))


def classify_primitive_usage(layer):
    primitive = get_primitive_info(layer.get("shape"))
    width = abs(float(layer.get("width") or 0))
    height = abs(float(layer.get("height") or 0))
    area = width * height
    ratio = max(width / height, height / width) if width and height else 0

    flags = []
    if area <= 16:
        flags.append("tiny")
    if ratio >= 12:
        flags.append("extremely_stretched")
    if primitive["id"] == "unknown":
        flags.append("unknown_shape")

    return {
        "primitive_id": primitive["id"],
        "category": primitive["category"],
        "visual_traits": primitive["visual_traits"],
        "usage_flags": flags,
        "layer_cost": primitive["layer_cost"],
    }


def describe_issue_with_primitive(layer, problem_type):
    primitive = get_primitive_info(layer.get("shape"))
    usage = classify_primitive_usage(layer)
    replacements = suggest_replacements(primitive["id"], problem_type)

    return {
        "current_primitive": primitive["id"],
        "primitive_traits": primitive["visual_traits"],
        "possible_replacements": replacements,
        "primitive_reason": _reason(layer, primitive, usage, problem_type),
    }


def _reason(layer, primitive, usage, problem_type):
    if problem_type == "duplicate_layer":
        return "This primitive appears redundant at the same position, size, color, and rotation."
    if problem_type == "very_small_layer":
        return f"{primitive['display_name']} is being used as a tiny patch; this often creates noisy fragmentation."
    if problem_type == "extremely_stretched_layer":
        return f"{primitive['display_name']} is highly stretched; a stroke-like or tapered primitive may be cleaner."
    if problem_type == "nearly_identical_colors":
        return "Nearby color variants may be mergeable into a simpler color decision."
    if problem_type == "edge_fixing_fragment":
        return f"{primitive['display_name']} is acting like edge cleanup; a line, arc, or polygon may express the edge more cleanly."
    if "unknown_shape" in usage["usage_flags"]:
        return "The parser does not know this primitive yet, so FLO can only make debug-level suggestions."
    return f"{primitive['display_name']} usage should be reviewed for a cleaner primitive choice."


def _normalize_shape_id(shape_id):
    if not shape_id:
        return "unknown"
    return str(shape_id).strip().lower().replace(" ", "_")


def _normalize_problem_type(problem_type):
    mapping = {
        "very_small_layer": "tiny_invisible_detail",
        "extremely_stretched_layer": "extreme_stretch",
        "edge_fixing_fragment": "possible_line_replacement",
        "messy_small_layer_cluster": "excessive_small_fragments",
    }
    return mapping.get(problem_type, problem_type)
