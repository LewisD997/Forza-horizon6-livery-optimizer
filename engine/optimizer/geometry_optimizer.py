import copy


def optimize_geometry_noop(geometry: dict, options: dict | None = None) -> dict:
    options = options or {}
    optimized = copy.deepcopy(geometry)
    input_count = len(geometry.get("shapes", [])) if isinstance(geometry, dict) else 0
    output_count = len(optimized.get("shapes", [])) if isinstance(optimized, dict) else 0
    return {
        "geometry": optimized,
        "report": {
            "input_shape_count": input_count,
            "output_shape_count": output_count,
            "changed_shape_count": 0,
            "removed_shape_count": 0,
            "added_shape_count": 0,
            "optimization_mode": "noop",
            "safety_level": "safe",
            "options": options,
        },
    }
