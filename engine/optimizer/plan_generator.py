from engine.optimizer.change_plan import make_change_entry, make_optimization_plan


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
                    risk_level="low",
                    status="proposed",
                    before=shape,
                    after=shape,
                    rollback={"action": "none", "reason": "mark_candidate does not modify geometry"},
                    metadata={"generated_by": "generate_noop_plan", "example": True},
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
