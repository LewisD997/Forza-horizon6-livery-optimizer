# Paint Studio Source-Grounded Preview Renderer

v0.5.9 adds a dedicated Paint Studio-compatible preview renderer for diagnostic use.

The old FLO preview renderer draws normalized layers with broad assumptions. That is useful for `.jsdn` and early MVP checks, but it is not faithful enough for real Paint Studio `geometry.json` files.

This renderer uses the source-confirmed semantics documented in:

```text
docs/paint_studio_source_renderer_audit.md
database/paint_studio_geometry_semantics.json
```

## What It Changes

- It reads Paint Studio `geometry.json` directly.
- It treats `shapes[0]` as the Paint Studio background fill.
- It renders `shapes[1:]` in array order.
- It handles Type 2 and Type 16 as center-based geometry.
- It renders Type 32 triangles from exact vertex points.
- It uses RGBA color semantics with straight alpha.
- It composites in linear light, then saves an RGBA PNG.
- It supports simple SSAA with `--ssaa 1`, `--ssaa 2`, or `--ssaa 4`.

v0.5.10 adds export alignment modes:

- `full_canvas_opaque`
- `full_canvas_transparent`
- `cropped_transparent`
- `cropped_transparent_with_padding`

These modes are for comparing FLO output against Paint Studio library preview exports, which may be transparent or cropped.

## Source-Confirmed Shape Semantics

Type 1 Rectangle:

```text
shapes[0] is background. Paint Studio fills the full canvas from shapes[0].Color RGB.
```

Later Type 1 shapes are rendered as best-effort `x, y, width, height` rectangles.

Type 2 RotatedRectangle:

```text
[cx, cy, halfW, halfH, thetaDeg]
```

Type 16 RotatedEllipse:

```text
[cx, cy, rx, ry, thetaDeg]
```

Type 32 Triangle:

```text
[x1, y1, x2, y2, x3, y3]
```

## Run On A Case

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 2
```

Export-alignment example:

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 4 --export-mode cropped_transparent --make-side-by-side
```

Run all export variants:

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 4 --run-export-variants
```

It writes:

```text
cases/case_0001/source_renderer/paintstudio_source_renderer_preview.png
cases/case_0001/source_renderer/paintstudio_source_renderer_diff.png
cases/case_0001/source_renderer/paintstudio_source_renderer_report.json
```

## Run The Fixture Smoke Test

```bash
python scripts/test_paintstudio_source_renderer.py
```

The fixture is synthetic and contains no real case assets.

## Why It May Still Differ From Paint Studio

This renderer is source-grounded, but it is still a Python diagnostic renderer.

Remaining mismatch can still come from:

- exact raster edge coverage differences
- Studio preview using `ss=1` while FLO diagnostics use SSAA
- gradient, mask, glow, disk, or unsupported shape types
- canvas preparation differences from Paint Studio crop/pad/maxRes logic
- any shape types not implemented in v0.5.9

This version does not modify geometry and does not perform Anime Cleanup.

Export alignment notes:

```text
docs/paint_studio_preview_export_alignment.md
```
