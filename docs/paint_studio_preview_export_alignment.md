# Paint Studio Preview Export Alignment

v0.5.9 fixed the biggest geometry mismatch by rendering Paint Studio `geometry.json` with source-confirmed semantics. Character structure is now much closer, but preview export alignment can still be wrong.

v0.5.10 focuses only on preview/export alignment. It does not implement Anime Cleanup and does not write optimized geometry.

## Why This Exists

Paint Studio's internal renderer treats `shapes[0]` as a background fill for normal preview rendering. Real library `preview.png` exports can still appear cropped or transparent, depending on how the preview was saved.

That means a full source-canvas FLO render can look structurally correct but still compare poorly against Paint Studio preview because:

- one image is full canvas while the other is cropped
- one image has opaque background while the other has transparency
- the dimensions differ, so comparison requires resizing
- RGB residual diffs exaggerate all channel errors and are hard to read

## Export Modes

The source renderer now supports:

- `full_canvas_opaque`: full source canvas with `shapes[0]` RGB as opaque background.
- `full_canvas_transparent`: full source canvas with transparent background.
- `cropped_transparent`: transparent render cropped to alpha/content bbox.
- `cropped_transparent_with_padding`: cropped transparent render with configurable padding.

Default behavior remains conservative: full canvas opaque.

## Run One Mode

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 4 --export-mode cropped_transparent
```

Useful options:

```text
--padding 8
--compare-preview
--make-side-by-side
```

## Run Export Variants

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 4 --run-export-variants
```

This writes:

```text
cases/case_0001/source_renderer/export_alignment_report.json
cases/case_0001/source_renderer/export_variants/
```

The report lists each variant's output size, alpha bbox, whether it directly matches Paint Studio preview dimensions, whether resizing was used for scoring, and difference scores when Paint Studio preview is available.

## Human-Friendly Diffs

When Paint Studio preview is available, the script writes:

```text
cases/case_0001/source_renderer/diffs/diff_rgb_residual.png
cases/case_0001/source_renderer/diffs/diff_abs_grayscale.png
cases/case_0001/source_renderer/diffs/diff_heatmap.png
cases/case_0001/source_renderer/diffs/diff_alpha.png
cases/case_0001/source_renderer/diffs/diff_overlay.png
```

Use them like this:

- `diff_rgb_residual`: raw channel residual, useful but harsh.
- `diff_abs_grayscale`: readable error strength map.
- `diff_heatmap`: quick human scan of high-error regions.
- `diff_alpha`: transparency mismatch.
- `diff_overlay`: visual alignment check.

If dimensions differ, the comparison records `resized_for_score: true`. Treat that score as less reliable.

## Interpretation

Prefer this order:

1. A variant with direct Paint Studio preview size match.
2. A low difference score without resizing.
3. A human-readable overlay/diff that looks spatially aligned.
4. Only then use resized scores as rough hints.

Remaining mismatch can still come from exact rasterization coverage, alpha blending details, Paint Studio crop/pad/maxRes behavior, or unsupported export semantics.
