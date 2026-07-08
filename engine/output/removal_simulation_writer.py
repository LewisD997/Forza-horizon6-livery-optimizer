import copy
import json
from pathlib import Path


class RemovalSimulationWriteError(Exception):
    pass


def write_removal_simulation_report(report, path, overwrite=False):
    validate_removal_simulation_report(report)
    output_path = Path(path)
    if output_path.exists() and not overwrite:
        raise RemovalSimulationWriteError(f"Removal simulation report already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = copy.deepcopy(report)
    serializable.pop("sandbox_geometry", None)
    output_path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(output_path)


def write_sandbox_geometry(geometry, path, overwrite=False):
    output_path = Path(path)
    if output_path.exists() and not overwrite:
        raise RemovalSimulationWriteError(f"Sandbox geometry already exists: {output_path}")
    _validate_geometry(geometry)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(geometry, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(output_path)


def validate_removal_simulation_report(report):
    if not isinstance(report, dict):
        raise RemovalSimulationWriteError("Removal simulation report must be an object.")
    required = {
        "simulation_version",
        "status",
        "input_shape_count",
        "accepted_candidate_count",
        "simulated_removed_count",
        "skipped_count",
        "output_shape_count",
        "removed_shapes",
        "skipped_candidates",
        "warnings",
    }
    missing = sorted(required - set(report))
    if missing:
        raise RemovalSimulationWriteError(f"Removal simulation report missing fields: {missing}")
    if report["status"] not in {"completed", "no_accepted_candidates", "completed_with_warnings", "failed"}:
        raise RemovalSimulationWriteError(f"Invalid simulation status: {report['status']}")
    expected_output_count = report["input_shape_count"] - report["simulated_removed_count"]
    if report["output_shape_count"] != expected_output_count:
        raise RemovalSimulationWriteError("Shape counts are inconsistent with simulated_removed_count.")
    if report["simulated_removed_count"] != len(report.get("removed_shapes", [])):
        raise RemovalSimulationWriteError("simulated_removed_count does not match removed_shapes length.")
    if report["accepted_candidate_count"] == 0 and report["simulated_removed_count"] != 0:
        raise RemovalSimulationWriteError("No accepted candidates should remove zero shapes.")
    if len(_removed_indexes(report)) != len(set(_removed_indexes(report))):
        raise RemovalSimulationWriteError("removed_shapes contains duplicate shape indexes.")
    return True


def _validate_geometry(geometry):
    if not isinstance(geometry, dict) or not isinstance(geometry.get("shapes"), list):
        raise RemovalSimulationWriteError("Geometry must contain a top-level shapes list.")
    for index, shape in enumerate(geometry["shapes"]):
        if not isinstance(shape, dict):
            raise RemovalSimulationWriteError(f"Shape {index} is not an object.")
        for field in ("type", "data", "color"):
            if field not in shape:
                raise RemovalSimulationWriteError(f"Shape {index} missing required field: {field}")


def _removed_indexes(report):
    return [item.get("shape_index") for item in report.get("removed_shapes", [])]
