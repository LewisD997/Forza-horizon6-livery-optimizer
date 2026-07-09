# Ablation Evidence Pack And Auto Triage

v0.6.10 adds evidence images and conservative auto triage for per-candidate ablation results.

It is still evidence-only. It does not approve cleanup, write official optimized geometry, update shapes, or modify Paint Studio files.

## Why This Exists

Full before/after preview images are too hard to judge when a candidate changes only a tiny local area.

v0.6.9 tells FLO whether a single candidate removal is safe-looking, probably safe, risky, failed, or not applicable. v0.6.10 makes that result easier to inspect by generating enlarged local crops, amplified diffs, overlays, and review cards.

## Generated Evidence

For each candidate, FLO writes:

- `before_crop.png`
- `after_crop.png`
- `diff_crop.png`
- `amplified_diff_crop.png`
- `candidate_mask_overlay.png`
- `before_after_side_by_side.png`
- `before_after_diff_card.png`
- `candidate_location_overview.png`
- `evidence_metadata.json`

It also writes:

- `ablation_evidence_sheet.png`
- `ablation_evidence_pack_report.json`
- `assistant_review_pack/assistant_review_manifest.json`
- `assistant_review_pack/assistant_review_sheet.png`
- `assistant_review_pack/assistant_review_summary.txt`

## Amplified Diff

The amplified diff boosts small pixel differences so they are visible to a human reviewer.

It is not a new metric. It is only a visual aid.

## Auto Triage Decisions

Triage labels:

- `safe_delete_candidate`: deletion looks tiny enough to consider later.
- `visible_but_minor`: change is visible but may be acceptable.
- `needs_replacement`: direct deletion is too visible; a future replacement or redraw may be needed.
- `protect_candidate`: deletion appears too risky; keep it.
- `unclear_needs_review`: metrics are incomplete or too close to a rule boundary.

`needs_replacement` is different from `safe_delete_candidate`: it means the layer may be messy or low quality, but deleting it directly creates a visible gap.

## Run

For a prepared case:

```bash
python scripts/generate_ablation_evidence_pack.py --case cases/case_0001 --upscale 6 --crop-padding 48
```

Validate:

```bash
python scripts/validate_ablation_evidence_pack.py --report cases/case_0001/removal_simulation/ablation/evidence_pack/ablation_evidence_pack_report.json
```

Single candidate:

```bash
python scripts/generate_ablation_evidence_pack.py --case cases/case_0001 --candidate-id C0011 --overwrite
```

## What To Upload For Review

Use:

```text
cases/case_0001/removal_simulation/ablation/evidence_pack/assistant_review_pack/assistant_review_sheet.png
cases/case_0001/removal_simulation/ablation/evidence_pack/assistant_review_pack/assistant_review_summary.txt
```

The summary asks:

```text
Please review whether these should be deleted, protected, or treated as replacement candidates.
```

## Safety

This version is non-destructive:

- original geometry is unchanged
- original `candidate_feedback.json` is unchanged
- no official `optimized_geometry.json` is written
- no replacement shapes are added
- no Anime Cleanup is implemented
- Paint Studio source and injection logic are untouched

`safe_delete_candidate` is still not final cleanup approval.

## Visible Contribution Follow-Up

After reviewing ablation evidence, run the visible contribution scanner to measure actual shape contribution by direct sandbox removal:

```bash
python scripts/scan_visible_contribution.py --case cases/case_0001
python scripts/validate_visible_contribution.py --report cases/case_0001/visible_contribution/visible_contribution_report.json
```

This writes `visible_contribution/` and can separate hidden or negligible shapes from shapes that need replacement or protection.
