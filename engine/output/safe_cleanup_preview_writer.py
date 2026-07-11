import json
from pathlib import Path


class SafeCleanupPreviewWriteError(Exception):
    pass


def write_preview_cleanup_geometry(geometry, path, overwrite=False, original_input_path=None):
    output = _guard(path, overwrite, original_input_path, geometry=True)
    _validate_geometry(geometry)
    _write_json(geometry, output)
    return str(output)


def write_safe_cleanup_apply_report(report, path, overwrite=False):
    output = _guard(path, overwrite)
    _write_json(report, output)
    return str(output)


def write_safe_cleanup_ledger(ledger, path, overwrite=False):
    output = _guard(path, overwrite)
    _write_json(ledger, output)
    return str(output)


def validate_preview_cleanup_output(original_geometry, preview_geometry, report):
    _validate_geometry(original_geometry)
    _validate_geometry(preview_geometry)
    applied = report.get("applied_removal_count", 0)
    if len(preview_geometry["shapes"]) != len(original_geometry["shapes"]) - applied:
        raise SafeCleanupPreviewWriteError("Preview shape count is inconsistent with applied removals.")
    if report.get("safety", {}).get("output_is_preview_only") is not True:
        raise SafeCleanupPreviewWriteError("Output is not marked preview-only.")
    return True


def _guard(path, overwrite, original_input_path=None, geometry=False):
    output = Path(path)
    if geometry and output.name.lower() == "optimized_geometry.json":
        raise SafeCleanupPreviewWriteError("Refusing official-looking filename optimized_geometry.json.")
    if original_input_path and output.resolve() == Path(original_input_path).resolve():
        raise SafeCleanupPreviewWriteError("Refusing to overwrite the original geometry path.")
    if output.exists() and not overwrite:
        raise SafeCleanupPreviewWriteError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _validate_geometry(geometry):
    if not isinstance(geometry, dict) or not isinstance(geometry.get("shapes"), list):
        raise SafeCleanupPreviewWriteError("Geometry must contain a top-level shapes list.")
    for index, shape in enumerate(geometry["shapes"]):
        if not isinstance(shape, dict) or not all(key in shape for key in ("type", "data", "color")):
            raise SafeCleanupPreviewWriteError(f"Invalid Paint Studio shape at index {index}.")


def _write_json(data, path):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
