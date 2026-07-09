# Per-Candidate Trial Ablation

v0.6.9 adds per-candidate trial ablation.

It tests trial accepted candidates one at a time, using sandbox geometry and preview diffs, so FLO can see which individual removal is safe-looking and which one caused a risky batch result.

## Why This Exists

v0.6.8 can test a small batch of trial accepted candidates. That is useful, but a risky batch only tells us the group was risky. It does not identify the candidate responsible for the visible change.

v0.6.9 runs the same removal and impact scoring path one candidate at a time.

## How It Works

For each candidate, FLO:

- creates `candidate_feedback_single.json`
- marks only that candidate as accepted in the temporary feedback copy
- runs sandbox removal
- writes sandbox geometry
- renders before and after previews
- writes a diff image
- scores removal impact
- records the candidate decision

The original Paint Studio geometry and original `candidate_feedback.json` are not modified.

## Run

For a prepared case:

```bash
python scripts/run_per_candidate_ablation.py --case cases/case_0001
```

Validate:

```bash
python scripts/validate_per_candidate_ablation.py --report cases/case_0001/removal_simulation/ablation/per_candidate_ablation_report.json
```

Explicit candidates:

```bash
python scripts/run_per_candidate_ablation.py --case cases/case_0001 --change-ids C0011,C0012
```

## Candidate Source Priority

Candidate selection follows this order:

1. `--change-ids`
2. `--trial-report`
3. default case trial report at `removal_simulation/trial/trial_workflow_report.json`
4. automatic conservative v0.6.8-style selection

Protected and rejected candidates are skipped.

## Outputs

The case output folder is:

```text
cases/case_0001/removal_simulation/ablation/
```

Each candidate gets its own folder:

```text
candidates/C0011/
  candidate_feedback_single.json
  sandbox_removed_geometry.json
  before_preview.png
  after_preview.png
  diff.png
  removal_simulation_report.json
  removal_impact_report.json
```

The top-level report is:

```text
per_candidate_ablation_report.json
per_candidate_ablation_summary.txt
```

## Reading The Report

Important fields:

- `candidate_count`
- `results[].change_id`
- `results[].removal.simulated_removed_count`
- `results[].impact.overall_decision`
- `results[].impact.changed_pixel_ratio`
- `summary.safe_to_remove`
- `summary.probably_safe`
- `summary.risky`
- `summary.failed`
- `batch_reference`

Compare `batch_reference.batch_decision` against each individual decision. If the batch was risky but individual candidates are safe or probably safe, the risk may come from combined removals. If a single candidate is risky, that candidate should stay protected until reviewed.

## Safety Reminder

`safe_to_remove` is still not final cleanup approval.

This workflow is diagnostic only. It does not write official `optimized_geometry.json`, does not update shape geometry, does not add replacements, and does not touch Paint Studio or injection logic.

## Future Use

Per-candidate ablation prepares FLO for a future safe cleanup proposal layer. That later layer should still require explicit review before writing any real optimized geometry.

## Evidence Pack Follow-Up

After running per-candidate ablation, generate enlarged review evidence:

```bash
python scripts/generate_ablation_evidence_pack.py --case cases/case_0001 --upscale 6 --crop-padding 48
python scripts/validate_ablation_evidence_pack.py --report cases/case_0001/removal_simulation/ablation/evidence_pack/ablation_evidence_pack_report.json
```

This writes `removal_simulation/ablation/evidence_pack/` and includes auto triage labels such as `needs_replacement`, `protect_candidate`, and `unclear_needs_review`.
