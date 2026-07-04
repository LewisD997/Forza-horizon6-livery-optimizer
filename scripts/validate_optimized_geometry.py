import argparse
import hashlib
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate a FLO optimized Paint Studio geometry file.")
    parser.add_argument("--input", required=True, help="Original Paint Studio geometry.json path.")
    parser.add_argument("--output", required=True, help="Optimized geometry output path.")
    args = parser.parse_args()

    try:
        result = validate_optimized_geometry(Path(args.input), Path(args.output))
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    print("Optimized geometry validation passed.")
    print(f"Input shapes: {result['input_shape_count']}")
    print(f"Output shapes: {result['output_shape_count']}")
    print(f"Input unchanged during validation: {result['input_unchanged_during_validation']}")
    return 0


def validate_optimized_geometry(input_path: Path, output_path: Path) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(f"Input geometry not found: {input_path}")
    if not output_path.exists():
        raise FileNotFoundError(f"Output geometry not found: {output_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    input_hash_before = _sha256(input_path)
    input_geometry = _load_geometry(input_path)
    output_geometry = _load_geometry(output_path)
    input_hash_after = _sha256(input_path)

    input_shapes = input_geometry["shapes"]
    output_shapes = output_geometry["shapes"]
    if len(input_shapes) != len(output_shapes):
        raise ValueError("Noop optimized geometry must preserve shape count.")

    for index, shape in enumerate(output_shapes):
        _validate_shape(shape, index)
        input_shape = input_shapes[index]
        for field in ("type", "data", "color", "score", "locked"):
            if field in input_shape and shape.get(field) != input_shape.get(field):
                raise ValueError(f"Shape {index} field changed unexpectedly: {field}")
        allowed = set(input_shape) | {"type", "data", "color", "score", "locked"}
        extra_fields = sorted(set(shape) - allowed)
        if extra_fields:
            raise ValueError(f"Shape {index} has unsupported schema fields: {extra_fields}")

    return {
        "input_shape_count": len(input_shapes),
        "output_shape_count": len(output_shapes),
        "input_unchanged_during_validation": input_hash_before == input_hash_after,
    }


def _load_geometry(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
        raise ValueError(f"Geometry must contain top-level shapes list: {path}")
    for index, shape in enumerate(data["shapes"]):
        _validate_shape(shape, index)
    return data


def _validate_shape(shape, index):
    if not isinstance(shape, dict):
        raise ValueError(f"Shape {index} is not an object.")
    for field in ("type", "data", "color"):
        if field not in shape:
            raise ValueError(f"Shape {index} is missing required field: {field}")
    if not isinstance(shape["data"], list):
        raise ValueError(f"Shape {index} data must be a list.")
    if not isinstance(shape["color"], list):
        raise ValueError(f"Shape {index} color must be a list.")


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
