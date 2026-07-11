# Safe Cleanup Apply Preview

v0.6.13 turns a validated `safe_delete_pool` proposal into a separate, clearly labeled preview geometry. It does not approve or write an official optimized livery.

The workflow has three distinct stages: a cleanup proposal records validated removals; preview apply revalidates identity and safety and removes eligible shapes from a deep copy; official optimized output is not implemented yet.

Every removal must use proposal version 0.6.12, have `requires_final_apply: true`, use the zero/negligible contribution reason, match the original `shape_uid`, match the visible-contribution report, avoid protected/rejected feedback, and stay out of protect/replacement/review groups. Multiple entries are validated against the original geometry and removed by descending original index. Remaining layer order is unchanged.

The application ledger stores each original shape, original index, evidence, checks, removal order, and a complete rollback payload. `rollback_preview_geometry.json` is reconstructed from the preview geometry plus this ledger and must be semantically identical to the input, including unknown fields.

```bash
python scripts/apply_safe_cleanup_preview.py --case cases/case_0001 --overwrite --write-rollback-preview
python scripts/validate_safe_cleanup_apply_preview.py --report cases/case_0001/safe_cleanup_apply_preview/safe_cleanup_apply_preview_report.json --original cases/case_0001/paintstudio_geometry.json
```

The renderer produces before, after, diff, and evidence images. When the source image is available, FLO also compares both previews against it using the existing resize alignment. An unavailable reference comparison is recorded without failing the workflow.

`preview_safe_cleanup_geometry.json` is preview-only and must not be treated as approved output. FLO never overwrites the original Paint Studio geometry. v0.6.13 closes the v0.6 safe-cleanup foundation; the next stage is v0.7.0 Semantic Region Map and Layer Attribution.
