# Feedback-Aware Review Visualization

v0.6.5 makes candidate review images aware of human feedback.

This version is still non-destructive. It does not delete layers, update shape data, add replacement shapes, write optimized cleanup geometry, modify Paint Studio source, or touch injection logic.

## Why This Exists

v0.6.4 added `candidate_feedback.json`, but review images still mostly looked like plain candidate diagnostics.

v0.6.5 makes accepted, rejected, protected, and unsure decisions visible in overlays, contact sheets, summaries, CSV files, and review indexes. This makes human review easier before any future cleanup logic exists.

## Run

Auto-load feedback from the case review folder:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --show-feedback
```

Use a specific feedback file:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --feedback cases/case_0001/candidate_review/candidate_feedback.json
```

Filter by feedback status:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --feedback-status unsure
python scripts/render_candidate_review.py --case cases/case_0001 --feedback-status protected
```

Disable feedback display:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --hide-feedback
```

## Feedback Statuses

- `accepted`: candidate may be tested later.
- `rejected`: candidate should not be removed.
- `protected`: future cleanup must not touch this candidate.
- `unsure`: candidate needs more review.

The visualizer uses both color and text labels. It does not rely on color alone.

## Feedback Outputs

When feedback exists, the renderer writes:

```text
candidate_overlay_feedback_all.png
candidate_overlay_feedback_accepted.png
candidate_overlay_feedback_rejected.png
candidate_overlay_feedback_protected.png
candidate_overlay_feedback_unsure.png
candidate_contact_sheet_feedback_all.png
candidate_contact_sheet_feedback_accepted.png
candidate_contact_sheet_feedback_rejected.png
candidate_contact_sheet_feedback_protected.png
candidate_contact_sheet_feedback_unsure.png
candidate_review_feedback_table.csv
```

Each contact sheet tile includes:

- change id
- shape index
- candidate type
- candidate score
- risk level
- feedback status
- reviewer note preview when available

## Index And Summary

`candidate_review_index.json` includes:

- `feedback_available`
- `feedback_path`
- `feedback_counts_by_status`
- `outputs_by_feedback_status`
- reviewed and unreviewed counts
- accepted, rejected, protected, and unsure counts
- feedback mismatch warnings

`review_summary.txt` includes the same feedback meaning in plain text.

## Warnings

The renderer warns when:

- a feedback item points to a `change_id` not present in the plan
- a plan candidate has no feedback item
- a feedback item's `shape_uid` does not match the plan

Warnings are diagnostic only.

## Cleanup Safety

`protected` is intentionally strong language. Future cleanup code must treat protected candidates as untouchable unless the user explicitly changes that feedback.

v0.6.5 only improves review visibility. It does not apply cleanup.
