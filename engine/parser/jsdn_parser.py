import json
from pathlib import Path


class JsdnParseError(Exception):
    pass


def parse_jsdn(path):
    source_path = Path(path)
    if not source_path.exists():
        raise JsdnParseError(f"Input file not found: {source_path}")

    raw_text = source_path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        dump_path = _write_debug_dump(source_path, raw_text, f"JSON parse failed: {exc}")
        raise JsdnParseError(
            f"Unknown .jsdn format. FLO currently expects readable JSON. Debug dump saved to {dump_path}"
        ) from exc

    raw_layers = _find_layers(data)
    if raw_layers is None:
        dump_path = _write_debug_dump(
            source_path,
            json.dumps(data, indent=2, ensure_ascii=False),
            "JSON loaded, but no layer list was found.",
        )
        raise JsdnParseError(
            f"Could not find layers in .jsdn JSON. Debug dump saved to {dump_path}"
        )

    return [_normalize_layer(layer, index) for index, layer in enumerate(raw_layers)]


def _find_layers(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return None

    candidate_keys = ("layers", "Layers", "vinyls", "objects", "shapes")
    for key in candidate_keys:
        value = data.get(key)
        if isinstance(value, list):
            return value

    for value in data.values():
        if isinstance(value, dict):
            nested = _find_layers(value)
            if nested is not None:
                return nested

    return None


def _normalize_layer(layer, index):
    if not isinstance(layer, dict):
        layer = {"value": layer}

    return {
        "id": str(_pick(layer, ("id", "uuid", "name", "layerId"), f"layer_{index + 1}")),
        "shape": str(_pick(layer, ("shape", "type", "primitive", "kind"), "unknown")),
        "x": _number(_pick(layer, ("x", "left", "posX", "positionX"), 0)),
        "y": _number(_pick(layer, ("y", "top", "posY", "positionY"), 0)),
        "width": _number(_pick(layer, ("width", "w", "scaleX", "sizeX"), 0)),
        "height": _number(_pick(layer, ("height", "h", "scaleY", "sizeY"), 0)),
        "rotation": _number(_pick(layer, ("rotation", "angle", "rot"), 0)),
        "color": _normalize_color(_pick(layer, ("color", "fill", "fillColor", "hex"), "#000000")),
        "opacity": _opacity(_pick(layer, ("opacity", "alpha"), 1)),
        "raw": layer,
    }


def _pick(data, keys, default):
    for key in keys:
        if key in data:
            return data[key]
    return default


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _opacity(value):
    number = _number(value)
    if number > 1:
        number = number / 100
    return max(0.0, min(1.0, number))


def _normalize_color(value):
    if isinstance(value, dict):
        r = int(_number(value.get("r", 0)))
        g = int(_number(value.get("g", 0)))
        b = int(_number(value.get("b", 0)))
        return f"#{_clamp_channel(r):02x}{_clamp_channel(g):02x}{_clamp_channel(b):02x}"

    text = str(value).strip()
    if text.startswith("#") and len(text) in (4, 7):
        return text.lower()
    return text


def _clamp_channel(value):
    return max(0, min(255, value))


def _write_debug_dump(source_path, content, reason):
    debug_dir = source_path.parent / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    dump_path = debug_dir / f"{source_path.stem}_debug_dump.txt"
    dump_path.write_text(f"{reason}\n\n--- source preview ---\n{content[:5000]}", encoding="utf-8")
    return dump_path
