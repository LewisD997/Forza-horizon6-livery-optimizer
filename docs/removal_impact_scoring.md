# Removal Impact Scoring

v0.6.7 scores the visual impact of sandbox candidate removal.

It only evaluates sandbox output. It does not approve final cleanup, write official optimized geometry, modify original geometry, or change Paint Studio files.

## Why This Exists

v0.6.6 can simulate removing accepted candidates from a copied geometry file. v0.6.7 adds the next safety layer: compare `before_preview.png` and `after_preview.png` and estimate whether the simulated removal looks safe, probably safe, or risky.

## Run

For a prepared case:

```bash
python scripts/score_removal_impact.py --case cases/case_0001
python scripts/validate_removal_impact.py --report cases/case_0001/removal_simulation/removal_impact_report.json
```

Explicit paths:

```bash
python scripts/score_removal_impact.py --removal-report cases/case_0001/removal_simulation/removal_simulation_report.json --before cases/case_0001/removal_simulation/before_preview.png --after cases/case_0001/removal_simulation/after_preview.png --output cases/case_0001/removal_simulation/removal_impact_report.json
```

The removal simulator can also run scoring:

```bash
python scripts/simulate_accepted_removal.py --case cases/case_0001 --score-impact
```

## Metrics

The scorer computes:

- mean absolute RGB difference
- max absolute RGB difference
- changed pixel count
- changed pixel ratio
- RGB changed pixel ratio
- alpha changed pixel ratio
- changed pixel bounding box
- local diff around each removed candidate region

Per removed shape metrics include change id, shape index, shape uid, candidate type, risk level, feedback status, region, and local decision.

## Decisions

Conservative default thresholds:

```text
safe_changed_pixel_ratio = 0.002
probably_safe_changed_pixel_ratio = 0.01
risky_changed_pixel_ratio = 0.03
```

Decision labels:

- `safe_to_remove`: global and local changes are very small.
- `probably_safe`: global change is small, but local change may be visible.
- `risky`: global or local change is too large.
- `not_applicable`: no accepted removals were simulated.
- `failed`: scoring inputs were missing, mismatched, or invalid.

These labels are diagnostic only. They do not authorize final cleanup.

## No Accepted Candidates

If no accepted candidates exist, the simulator does not create an after preview or diff. In that case impact scoring returns:

```text
status = not_applicable_no_removals
overall_decision = not_applicable
```

That is expected and safe.

## Next Step

The next step should be a safe cleanup proposal layer. It should still require explicit review before writing any final optimized geometry.
