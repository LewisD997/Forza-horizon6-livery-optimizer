# Paint Studio Renderer Compatibility Debugging

This diagnostic exists because real Paint Studio `geometry.json` can render very differently in FLO's current preview renderer.

If Paint Studio preview looks good but FLO preview looks wrong, the case should be treated as a renderer compatibility case first. It should not be used as anime cleanup training evidence yet.

## Why This Step Is Necessary

FLO's visual diff and anime artifact scores depend on the rendered preview.

If the renderer is wrong, then downstream signals are also wrong:

- visual difference score may punish the wrong thing
- anime artifact regions may flag renderer errors as livery errors
- optimization suggestions may point at fake problems
- rule evidence may become polluted

Renderer compatibility must come before cleanup planning.

## Possible Causes

Common mismatch causes include:

- alpha parsing or opacity direction
- color channel order, such as RGB vs BGR
- layer order, such as front-to-back vs back-to-front
- unsupported mask, glyph, or gradient shapes
- canvas, crop, scale, or coordinate mismatch
- background layer handling
- Paint Studio center-based geometry being interpreted as top-left geometry

## Run The Diagnostic

For a prepared case:

```bash
python scripts/diagnose_paintstudio_renderer.py --case cases/case_0001
```

The script expects:

```text
cases/case_0001/source_full.png
cases/case_0001/paintstudio_geometry.json
cases/case_0001/paintstudio_preview.png
```

It writes:

```text
cases/case_0001/renderer_diagnostic/
  renderer_diagnostic_report.json
  shape_type_summary.txt
  color_alpha_summary.txt
  render_variants/
    current_renderer.png
    reversed_layer_order.png
    rgb_no_alpha_test.png
    bgr_channel_test.png
    alpha_ignored_test.png
    alpha_inverted_test.png
```

## Render Variants

- `current_renderer.png`: current FLO preview behavior.
- `reversed_layer_order.png`: same parsed shapes in reverse order.
- `rgb_no_alpha_test.png`: RGB color, opacity forced to 1.
- `bgr_channel_test.png`: RGB/BGR channel swap.
- `alpha_ignored_test.png`: parsed RGB, non-background opacity forced to 1.
- `alpha_inverted_test.png`: alpha interpreted as `1 - alpha/255`.

These variants are diagnostic only. They do not change the default FLO renderer.

## How To Interpret Results

Use Paint Studio preview comparison first when the preview dimensions match `source_full.png`.

If Paint Studio preview dimensions do not match, the comparison is marked unreliable because the preview may be a UI screenshot, crop, or scaled export.

The source image comparison is useful context, but it is not the same thing as checking whether FLO matches Paint Studio's renderer.

Signals to look for:

- `reversed_layer_order.png` closest: likely layer order issue.
- `bgr_channel_test.png` closest: likely channel order issue.
- `alpha_ignored_test.png` or `alpha_inverted_test.png` closest: likely alpha interpretation issue.
- all variants bad with many mask-like types: unsupported shape registry or mask rendering issue.
- all variants shifted or cropped: canvas, scale, or coordinate interpretation issue.

## Current Boundary

This is not Anime Cleanup.

It does not:

- modify geometry
- output optimized geometry
- change Paint Studio source
- change game injection logic
- train AI
- create cleanup candidates
