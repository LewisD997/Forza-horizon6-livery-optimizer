# Safe Delete Pool Batch Validator

v0.6.12 adds a sandbox-only batch validator for `safe_delete_pool`.

## Why This Exists

v0.6.11 can find shapes with zero or negligible visible contribution by removing them one at a time.

v0.6.12 asks the next question:

```text
If all safe_delete_pool shapes are removed together, is the result still visually safe?
```

This matters because several tiny changes can combine into a visible change. FLO should not turn a one-by-one metric into a cleanup action without checking the batch.

## Safe Delete Pool vs Review Candidates

`safe_delete_pool` is the narrowest deletion class. A shape must be:

- recommended as `safe_delete_pool`
- classified as `zero_or_negligible_contribution`
- tied to a matching current `shape_uid`
- removed as exactly one shape in the source scan
- not protected or rejected by feedback
- not listed as `protect_candidate`

The validator does not include:

- `deletion_candidate_review`
- `replacement_candidate`
- `protect_candidate`
- `unclear_needs_review`
- visible minor, important, or critical contribution classes

## How Batch Validation Works

The validator reads:

- Paint Studio `paintstudio_geometry.json`
- `visible_contribution_report.json`
- optional `candidate_feedback.json`

It then:

- copies geometry into a sandbox object
- removes all eligible `safe_delete_pool` shapes from that sandbox only
- preserves original order for remaining shapes
- renders before and after previews
- generates a visual diff
- runs removal impact scoring
- writes a cleanup proposal

The original geometry and feedback files are not changed.

## Output

For a prepared case:

```text
cases/case_0001/safe_delete_validation/
  safe_delete_pool_validation_report.json
  safe_delete_cleanup_proposal.json
  safe_delete_validation_summary.txt
  sandbox_safe_deleted_geometry.json
  before_preview.png
  after_preview.png
  diff.png
  removal_impact_report.json
  evidence_sheet.png
```

`sandbox_safe_deleted_geometry.json` is diagnostic only. It is not the official cleanup output.

## Cleanup Proposal

`safe_delete_cleanup_proposal.json` lists proposed removals and their evidence:

- change ID
- shape index
- shape UID
- single-shape visible contribution metrics
- batch impact summary
- low-risk proposal status

It also keeps:

```json
{
  "approval_required": true,
  "official_geometry_written": false
}
```

The proposal does not apply itself.

## Run

Case mode:

```bash
python scripts/validate_safe_delete_pool.py --case cases/case_0001 --overwrite
python scripts/validate_safe_delete_pool_report.py --report cases/case_0001/safe_delete_validation/safe_delete_pool_validation_report.json
```

Explicit paths:

```bash
python scripts/validate_safe_delete_pool.py --geometry cases/case_0001/paintstudio_geometry.json --visible-report cases/case_0001/visible_contribution/visible_contribution_report.json --output-dir cases/case_0001/safe_delete_validation --overwrite
```

Disable rendering for logic-only checks:

```bash
python scripts/validate_safe_delete_pool.py --case cases/case_0001 --no-render --overwrite
```

## Reading The Report

Key fields:

- `safe_delete_candidate_count`: number of eligible safe-delete candidates.
- `simulated_removed_count`: number actually removed from the sandbox.
- `input_shape_count` / `output_shape_count`: expected layer-count change.
- `impact_summary.overall_decision`: batch visual risk.
- `removed_shapes`: exact change IDs included.
- `skipped_candidates`: candidates blocked by safety rules.
- `safety`: confirms sandbox/proposal-only behavior.

## Why No Official Optimized Geometry Yet

v0.6.12 is still a validator.

It prepares a future final apply step, but does not write `optimized_geometry.json`, does not touch Paint Studio source, and does not modify injection logic.

The intended next step is a separate final-apply workflow that reads an approved proposal and writes official cleanup output only after explicit human approval.
