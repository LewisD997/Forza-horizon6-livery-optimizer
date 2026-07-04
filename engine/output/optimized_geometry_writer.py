import copy
import json
from datetime import datetime, timezone
from pathlib import Path


class OptimizedGeometryWriteError(Exception):
    pass


def write_optimized_geometry(
    input_geometry_path: str,
    output_geometry_path: str,
    shapes: list | None = None,
    metadata: dict | None = None,
    overwrite: bool = False,
) -> dict:
    input_path = Path(input_geometry_path)
    output_path = Path(output_geometry_path)
    if not input_path.exists():
        raise OptimizedGeometryWriteError(f"Input geometry does not exist: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise OptimizedGeometryWriteError("Refusing to overwrite the input geometry file.")
    if output_path.exists() and not overwrite:
        raise OptimizedGeometryWriteError(
            f"Output geometry already exists: {output_path}. Use --overwrite-output to replace it."
        )

    geometry = _read_geometry(input_path)
    output_geometry = copy.deepcopy(geometry)
    if shapes is not None:
        output_geometry["shapes"] = copy.deepcopy(shapes)

    _validate_geometry(output_geometry)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_geometry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    report = _build_report(input_path, output_path, geometry, output_geometry, metadata)
    report_path = output_path.with_name(f"{output_path.stem}_optimization_report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _read_geometry(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OptimizedGeometryWriteError(f"Invalid input geometry JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
        raise OptimizedGeometryWriteError("Paint Studio geometry must contain a top-level shapes list.")
    _validate_geometry(data)
    return data


def _validate_geometry(geometry):
    shapes = geometry.get("shapes")
    if not isinstance(shapes, list):
        raise OptimizedGeometryWriteError("Geometry must contain a shapes list.")
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            raise OptimizedGeometryWriteError(f"Shape {index} is not an object.")
        for field in ("type", "data", "color"):
            if field not in shape:
                raise OptimizedGeometryWriteError(f"Shape {index} is missing required field: {field}")
        if not isinstance(shape.get("data"), list):
            raise OptimizedGeometryWriteError(f"Shape {index} data must be a list.")
        if not isinstance(shape.get("color"), list):
            raise OptimizedGeometryWriteError(f"Shape {index} color must be a list.")


def _build_report(input_path, output_path, input_geometry, output_geometry, metadata):
    metadata = metadata or {}
    input_count = len(input_geometry.get("shapes", []))
    output_count = len(output_geometry.get("shapes", []))
    optimizer_report = metadata.get("optimizer_report") or {}
    report = {
        "input_geometry_path": str(input_path),
        "output_geometry_path": str(output_path),
        "optimization_mode": metadata.get("optimization_mode")
        or optimizer_report.get("optimization_mode")
        or "noop",
        "safety_level": metadata.get("safety_level") or optimizer_report.get("safety_level") or "safe",
        "input_shape_count": input_count,
        "output_shape_count": output_count,
        "changed_shape_count": optimizer_report.get("changed_shape_count", 0),
        "removed_shape_count": optimizer_report.get("removed_shape_count", max(0, input_count - output_count)),
        "added_shape_count": optimizer_report.get("added_shape_count", max(0, output_count - input_count)),
        "warnings": list(metadata.get("warnings", [])),
        "renderer_used": metadata.get("renderer_used"),
        "preview_paths": metadata.get("preview_paths", {}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_version": metadata.get("tool_version", "v0.6.0"),
        "metadata_storage": "separate_report_file",
        "notes": [
            "Optimized geometry is written as a separate file.",
            "FLO metadata is kept out of geometry.json for Paint Studio compatibility.",
        ],
    }
    return report
