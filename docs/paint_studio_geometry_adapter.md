# FLO v0.5.3 Paint Studio Geometry Adapter

This adapter lets FLO read Paint Studio `geometry.json` files as diagnostic input.

It does not modify Paint Studio files, game memory, or generated shapes.

## Supported Type Mappings

| Paint Studio type | FLO shape | Notes |
| --- | --- | --- |
| `1` | `rectangle` | Axis-aligned rectangle. |
| `2` | `rectangle` | Rotated rectangle. |
| `16` | `ellipse` | Rotated ellipse. Circles are ellipses with equal radii. |
| `32` | `triangle` | Three explicit points. |
| `64` | `line_internal_only` | Internal Paint Studio line geometry. |
| `0xe4` | `glow` | Native radial glow primitive. |
| `0xe2` | `disk` | Native radial disk primitive. |
| other numeric type | `mask_or_unknown` | Preserved as raw data for later registry work. |

## Conversion Assumptions

Rectangles, ellipses, glow, and disk shapes are treated as:

```text
[cx, cy, halfW/rx, halfH/ry, thetaDeg, _]
```

FLO converts those to:

```text
x = cx
y = cy
width = halfW * 2
height = halfH * 2
rotation = thetaDeg
```

Triangles are treated as:

```text
[x1, y1, x2, y2, x3, y3]
```

FLO stores the triangle center as `x/y`, stores the bounding box size as `width/height`, and preserves the original points in `raw`.

Paint Studio color arrays are converted to `#rrggbb`. If a fourth channel exists, it becomes FLO opacity from `0.0` to `1.0`.

## Known Limitations

- FLO does not yet render Paint Studio masks with the exact official bitmap shape.
- Unknown numeric shape words are preserved as `mask_or_unknown`.
- Glow and disk are approximated by the current preview renderer as debug boxes until a faithful renderer is added.
- Triangle preview is approximate because FLO's normalized layer schema is simpler than Paint Studio's point geometry.
- The adapter reads geometry for diagnostics only and does not write `geometry.json`.

## Why TypeLine Is Internal Only

Paint Studio defines `TypeLine = 64`, but its injector path documents that FH6 has no direct in-game line primitive. The injector skips line output instead of writing it as a layer.

FLO maps it to `line_internal_only` so reports can identify it without treating it as a safe injectable primitive.

## Diagnostic-Only Status

v0.5.3 exists so FLO can inspect Paint Studio outputs before Anime Cleanup exists.

It supports parser dispatch, preview generation, visual diff, layer analysis, primitive knowledge diagnostics, and suggestion reporting. It does not optimize, rewrite, inject, or export modified Paint Studio geometry.
