from engine.optimizer.change_plan import make_change_entry, make_optimization_plan
from engine.optimizer.candidate_planner import generate_cleanup_candidate_plan


def generate_noop_plan(
    geometry: dict,
    input_geometry_path: str,
    output_geometry_path: str | None = None,
    include_mark_candidates: bool = False,
    max_mark_candidates: int = 3,
) -> dict:
    shapes = geometry.get("shapes", []) if isinstance(geometry, dict) else []
    changes = []
    if include_mark_candidates:
        for index, shape in enumerate(shapes[:max_mark_candidates]):
            changes.append(
                make_change_entry(
                    change_id=f"C{index + 1:04d}",
                    action="mark_candidate",
                    shape_index=index,
                    shape=shape,
                    reason="Example non-destructive candidate marker for patch ledger testing.",
                    risk_level="review_only",
                    status="proposed",
                    before=shape,
                    after=shape,
                    rollback={"action": "none", "reason": "mark_candidate does not modify geometry"},
                    metadata={
                        "candidate_type": "unknown_review_candidate",
                        "candidate_score": 0.0,
                        "region": None,
                        "visual_diff_score": None,
                        "layer_alpha": _alpha(shape),
                        "layer_area_estimate": None,
                        "primitive_type": shape.get("type"),
                        "artifact_reasons": ["example_non_destructive_marker"],
                        "recommendation": "review_before_cleanup",
                        "human_review_required": True,
                        "generated_by": "generate_noop_plan",
                        "example": True,
                    },
                )
            )
    return make_optimization_plan(
        input_geometry_path=input_geometry_path,
        output_geometry_path=output_geometry_path,
        optimization_mode="noop_plan",
        shape_count_before=len(shapes),
        changes=changes,
        warnings=[],
        safety_level="safe",
    )


def generate_candidate_plan(
    geometry: dict,
    input_geometry_path: str,
    output_geometry_path: str | None = None,
    analysis_report: dict | None = None,
    options: dict | None = None,
) -> dict:
    return generate_cleanup_candidate_plan(
        geometry,
        analysis_report=analysis_report,
        options={
            **(options or {}),
            "input_geometry_path": input_geometry_path,
            "output_geometry_path": output_geometry_path,
        },
    )


def _alpha(shape):
    color = shape.get("color") if isinstance(shape, dict) else None
    if isinstance(color, list) and len(color) >= 4:
        try:
            return max(0.0, min(1.0, float(color[3]) / 255.0))
        except (TypeError, ValueError):
            return 1.0
    return 1.0
