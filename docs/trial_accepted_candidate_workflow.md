# Trial Accepted Candidate Workflow

v0.6.8 adds a temporary trial workflow for testing conservative candidate removals.

It creates a separate `candidate_feedback_trial.json`, marks a small number of safe-looking `unsure` candidates as trial accepted, and then runs sandbox removal plus impact scoring against that trial feedback.

It does not modify the original geometry or the original `candidate_feedback.json`.

## Purpose

The normal accepted-candidate simulator needs human feedback with `accepted` statuses. Early case studies may start with many `unsure` candidates, so v0.6.8 provides a controlled way to test a few conservative candidates without changing the real review record.

This keeps FLO read-only and diagnostic while making removal impact experiments easier.

## Safety Rules

The trial workflow:

- writes only under `removal_simulation/trial/`
- copies feedback into `candidate_feedback_trial.json`
- only changes eligible `unsure` items to trial `accepted`
- blocks `protected` and `rejected`
- checks shape uid consistency
- writes sandbox geometry only as `sandbox_removed_geometry_trial.json`
- does not overwrite original Paint Studio geometry
- does not modify original `candidate_feedback.json`
- does not write official cleanup or optimized geometry output

It does not:

- update position, scale, rotation, color, or alpha
- add replacement shapes
- apply Anime Cleanup
- modify Paint Studio source
- touch injection logic

## Run

For a prepared case:

```bash
python scripts/run_trial_accepted_workflow.py --case cases/case_0001 --max-trial-accepts 5
```

Validate the trial workflow report:

```bash
python scripts/validate_trial_workflow.py --report cases/case_0001/removal_simulation/trial/trial_workflow_report.json
```

Optionally validate the original feedback file stays valid:

```bash
python scripts/validate_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json --plan cases/case_0001/optimization_plan.json
```

## Outputs

The trial workflow writes to:

```text
cases/case_0001/removal_simulation/trial/
```

Typical outputs:

```text
candidate_feedback_trial.json
trial_feedback_report.json
sandbox_removed_geometry_trial.json
before_preview.png
after_preview.png
diff.png
removal_simulation_report_trial.json
removal_impact_report_trial.json
trial_workflow_report.json
trial_workflow_summary.txt
```

If no candidates are eligible, the workflow reports:

```text
status = no_eligible_trial_candidates
```

In that case no sandbox removal happens and impact scoring is marked not applicable.

## Candidate Selection

Default selection is conservative. It prefers:

- low-risk candidates
- tiny fragment cluster members
- very low alpha soft shapes
- low-risk ellipse cluster members
- small or moderate estimated area

By default it avoids:

- `protected` feedback
- `rejected` feedback
- already accepted feedback
- review-only risk
- very early shape indexes
- very large regions
- candidate types outside the conservative starter set

Explicit change IDs can be tested with:

```bash
python scripts/run_trial_accepted_workflow.py --case cases/case_0001 --change-ids C0001,C0002
```

Protected and rejected items are still blocked.

## Reading The Report

Important fields in `trial_workflow_report.json`:

- `status`
- `original_feedback_counts`
- `trial_feedback_counts`
- `selected_trial_candidates`
- `removal_summary.simulated_removed_count`
- `impact_summary.status`
- `impact_summary.overall_decision`
- `safety.original_geometry_modified`
- `safety.original_feedback_modified`
- `safety.official_cleanup_output_written`

The three safety fields above must remain:

```text
false
false
false
```

## Per-Candidate Follow-Up

If a trial batch is risky, run per-candidate ablation to isolate which candidate caused the visible change:

```bash
python scripts/run_per_candidate_ablation.py --case cases/case_0001
python scripts/validate_per_candidate_ablation.py --report cases/case_0001/removal_simulation/ablation/per_candidate_ablation_report.json
```

This writes under `removal_simulation/ablation/` and still does not modify original geometry or original feedback.

## Diagnostic Only

This workflow is a rehearsal path, not cleanup approval.

The trial output is useful for comparing before/after previews and checking whether a candidate class may be harmless. It should not be treated as permission to write final optimized geometry.
