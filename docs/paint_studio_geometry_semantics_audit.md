# Paint Studio Geometry Semantics Audit

v0.5.6 showed that FLO's Paint Studio preview mismatch is not solved by simple render variants.

The case_0001 Paint Studio preview now uses the real Paint Studio library preview, not a UI screenshot. FLO preview is still far away, so the problem is deeper than screenshot comparison.

## Why v0.5.6 Was Not Enough

v0.5.6 tested:

- reversed layer order
- alpha ignored
- alpha inverted
- RGB/BGR channel swap
- current renderer output

Those variants still did not visually match Paint Studio preview. That means the current renderer mismatch may come from geometry semantics, not just color or opacity handling.

## Why Render Variants Are Not Trusted Yet

The variants are useful probes, but they are not proof.

For example, `reversed_layer_order` can score better because it accidentally changes large color coverage, not because Paint Studio truly stores all layers front-to-back.

Until geometry meanings are confirmed, visual diff and anime artifact scores should not be used as cleanup evidence for this case.

## Layer Slices

Run:

```bash
python scripts/debug_paintstudio_geometry_layers.py --case cases/case_0001
```

Layer slices are written to:

```text
cases/case_0001/geometry_debug/layer_slices/
```

Use them to inspect layer order:

- `first_001_layers.png` only background, then `first_010/050/100` gradually building the image suggests back-to-front order.
- `last_001/010/050/100` containing background or large base shapes suggests ordering assumptions may be wrong.
- `all_layers.png` shows the current diagnostic interpretation of every layer.

## Type Isolation

Type isolation images are written to:

```text
cases/case_0001/geometry_debug/type_isolation/
```

They isolate:

- Type `1`: rectangle only
- Type `2`: rotated rectangle only
- Type `16`: ellipse only
- Type `32`: triangle only

This helps identify which primitive interpretation is most wrong.

## Background Tests

Background tests are written to:

```text
cases/case_0001/geometry_debug/background_tests/
```

The first TypeRectangle background is rendered as:

- `background_as_xywh.png`
- `background_as_xyxy.png`
- `background_ignored.png`

This checks whether TypeRectangle data with four values should be interpreted as `x, y, width, height` or `x1, y1, x2, y2`.

## Semantics Hints

Current hypotheses:

- TypeRectangle with 4 values may be `x/y/width/height` or `x1/y1/x2/y2`.
- TypeRotatedRectangle with 5 values may be `cx/cy/halfW/halfH/theta`.
- TypeRotatedEllipse with 5 values may be `cx/cy/rx/ry/theta`.
- TypeTriangle with 6 values likely means `x1/y1/x2/y2/x3/y3`.

These are still diagnostic hypotheses.

## Real Case Assets

Real case files should not be committed:

- source images
- Paint Studio geometry
- Paint Studio previews
- FLO previews
- diff images
- generated diagnostic PNGs

`cases/case_*/` is ignored so real case assets stay local, while `cases/case_template/` remains tracked.

## Current Boundary

This audit does not implement Anime Cleanup.

It does not:

- output optimized geometry
- change the default renderer
- change Paint Studio source
- change injection logic
- create cleanup candidates
