# Visible Contribution Scanner

v0.6.11 adds a sandbox-only visible contribution scanner.

It answers a different question from the candidate planner.

Candidate planner asks:

```text
Does this shape look suspicious?
```

Visible contribution scanner asks:

```text
If this exact shape is removed, how much does the final rendered image actually change?
```

## Why This Exists

v0.6.10 showed that low-alpha shapes are not automatically safe to delete. A shape can look weak or messy in metadata, but still carry visible shading, edge smoothing, or local structure.

The scanner directly removes one shape at a time from a sandbox copy, renders before/after previews, and measures actual pixel contribution.

## What It Detects

The scanner can identify:

- mostly hidden or occluded shapes
- visually negligible shapes
- tiny but real contribution
- visible minor contribution
- important visible contribution
- critical contribution that should be protected

## Contribution Classes

- `zero_or_negligible_contribution`
- `barely_visible_contribution`
- `visible_minor_contribution`
- `important_visible_contribution`
- `critical_contribution`
- `scan_failed`

## Recommended Actions

- `safe_delete_pool`: good candidate for a future delete proposal.
- `deletion_candidate_review`: maybe removable, but needs review.
- `replacement_candidate`: direct deletion is too visible; future redraw/replacement may be needed.
- `protect_candidate`: keep it.
- `unclear_needs_review`: metrics or rendering were not clear enough.

Low alpha does not equal safe delete. Only actual visible contribution metrics can put a shape into `safe_delete_pool`.

## Safe Delete Pool Batch Validation

v0.6.12 adds a second check after visible contribution scanning.

`safe_delete_pool` is not final cleanup approval. Before FLO can propose deletion, all safe-delete shapes are removed together in a sandbox copy and rescored as a batch.

Run:

```bash
python scripts/validate_safe_delete_pool.py --case cases/case_0001 --overwrite
python scripts/validate_safe_delete_pool_report.py --report cases/case_0001/safe_delete_validation/safe_delete_pool_validation_report.json
```

This writes:

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

The cleanup proposal is still proposal-only. FLO does not write official `optimized_geometry.json` in v0.6.12.

## Run

Default low-risk candidate scan:

```bash
python scripts/scan_visible_contribution.py --case cases/case_0001
```

Explicit prior candidates:

```bash
python scripts/scan_visible_contribution.py --case cases/case_0001 --scope explicit --change-ids C0011,C0012,C0013,C0014,C0018 --output-dir cases/case_0001/visible_contribution/focused_v0610_candidates --overwrite
```

Validate:

```bash
python scripts/validate_visible_contribution.py --report cases/case_0001/visible_contribution/visible_contribution_report.json
```

## Outputs

```text
cases/case_0001/visible_contribution/
  visible_contribution_report.json
  visible_contribution_summary.txt
  visible_contribution_table.csv
  baseline_preview.png
  evidence_sheet.png
  shapes/
```

Each scanned shape gets:

```text
after_preview.png
diff.png
diff_crop.png
amplified_diff_crop.png
evidence_card.png
contribution_metadata.json
```

## Safety

This is non-destructive:

- original geometry is unchanged
- original `candidate_feedback.json` is unchanged
- no official `optimized_geometry.json` is written
- no replacement shapes are added
- no Anime Cleanup or eye reconstruction is implemented
- Paint Studio source and injection logic are untouched

The scanner prepares FLO for semantic region analysis and a future cleanup proposal layer. It does not approve cleanup by itself.

v0.6.13 uses this scanner's exact `change_id`, `shape_uid`, contribution class, and recommended action when revalidating a safe-delete proposal for preview-only application. Zero/negligible contribution remains evidence rather than official cleanup approval.
