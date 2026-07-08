# Accepted Candidate Sandbox Removal

v0.6.6 adds a safety-first removal simulator.

It only tests what would happen if candidates with feedback status `accepted` were removed from a sandbox copy of Paint Studio geometry.

It does not modify the original geometry.

## Why This Exists

FLO now has candidate plans, review images, and human feedback. The next safe step is not real cleanup. The next safe step is a sandbox simulation that answers one question:

What changes if only accepted candidates are removed from a copy?

## Safety Rules

The simulator:

- only considers `accepted` feedback
- blocks `protected`
- blocks `rejected`
- blocks `unsure`
- skips shape uid mismatches
- skips out-of-range shape indexes
- removes duplicate accepted shape indexes only once
- never mutates the input geometry object
- preserves order for all remaining shapes

It does not:

- update shape data
- add replacement shapes
- adjust position, scale, rotation, color, or alpha
- overwrite the original Paint Studio geometry
- modify Paint Studio source
- touch injection logic

## Run

For a prepared case:

```bash
python scripts/simulate_accepted_removal.py --case cases/case_0001
```

Explicit paths:

```bash
python scripts/simulate_accepted_removal.py --geometry cases/case_0001/paintstudio_geometry.json --plan cases/case_0001/optimization_plan.json --feedback cases/case_0001/candidate_review/candidate_feedback.json --output-dir cases/case_0001/removal_simulation
```

Limit removals:

```bash
python scripts/simulate_accepted_removal.py --case cases/case_0001 --max-removals 5
```

Dry run:

```bash
python scripts/simulate_accepted_removal.py --case cases/case_0001 --dry-run
```

## Outputs

The case output folder is:

```text
cases/case_0001/removal_simulation/
```

It may contain:

```text
removal_simulation_report.json
sandbox_removed_geometry.json
before_preview.png
after_preview.png
diff.png
removal_simulation_summary.txt
```

If there are no accepted candidates, the report status is:

```text
no_accepted_candidates
```

In that case no removal is simulated. `after_preview.png` and `diff.png` are not generated because they would be misleading.

## Validate

```bash
python scripts/validate_removal_simulation.py --report cases/case_0001/removal_simulation/removal_simulation_report.json --geometry cases/case_0001/paintstudio_geometry.json
```

Score visual impact:

```bash
python scripts/score_removal_impact.py --case cases/case_0001
python scripts/validate_removal_impact.py --report cases/case_0001/removal_simulation/removal_impact_report.json
```

Validation checks:

- required report fields exist
- original geometry is marked unchanged
- input and output shape counts are consistent
- no accepted candidates means zero removals
- removed shape indexes are unique
- removed shapes only come from accepted feedback
- sandbox geometry count matches the report when present

## Reading The Report

Important fields:

- `status`: completed, no accepted candidates, completed_with_warnings, or failed
- `accepted_candidate_count`: number of accepted feedback candidates considered
- `simulated_removed_count`: number of shapes removed from the sandbox copy
- `skipped_candidates`: accepted candidates that were not safe to remove
- `warnings`: safety notes
- `safety.original_geometry_modified`: must be false

## Next Step

Impact scoring is documented in:

```text
docs/removal_impact_scoring.md
```

After that, the next step should be a safe cleanup proposal layer before any real cleanup output exists.
