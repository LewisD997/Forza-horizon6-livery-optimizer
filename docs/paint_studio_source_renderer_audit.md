# Paint Studio Source-Grounded Renderer Audit

## Why this audit was needed

FLO's diagnostic renderer still mismatches Paint Studio preview for `case_0001`.

v0.5.6 and v0.5.7 showed that simple guesses are not enough:

- reversed layer order did not fix the render
- alpha ignored / alpha inverted did not fix the render
- RGB/BGR swap did not fix the render
- Paint Studio library preview is now the real preview, not a UI screenshot

So v0.5.8 inspects Paint Studio source code directly before changing FLO's renderer.

## Source files inspected

- `research/fh6-paint-studio/internal/model/model.go`
  - Shape type constants, `Shape`, `Geometry`, `Candidate.ToShape`, `KindFromType`, `ParamsFromShape`.
- `research/fh6-paint-studio/internal/model/color.go`
  - sRGB/linear conversion and stored byte color rules.
- `research/fh6-paint-studio/internal/imageio/output.go`
  - `WriteGeometry`, `ReadGeometry`, `RenderFH6`, `RenderFH6Image`, `SavePreview`, alpha compositing, SSAA.
- `research/fh6-paint-studio/internal/raster/raster.go`
  - Rectangle, ellipse, triangle, and line geometry tests and bounding boxes.
- `research/fh6-paint-studio/internal/raster/gradient.go`
  - Glow/disk per-pixel alpha coverage rules.
- `research/fh6-paint-studio/internal/imageio/imageio.go`
  - Source loading, max-res scaling, padding, unpadding, shape translation.
- `research/fh6-paint-studio/internal/engine/run.go`
  - Background shape creation and geometry initialization.
- `research/fh6-paint-studio/internal/runner/runner.go`
  - Studio final preview uses `imageio.RenderFH6Image`.
- `research/fh6-paint-studio/internal/library/library.go`
  - Library writes `geometry.json`, `preview.png`, `thumb.png`, `meta.json`.
- `research/fh6-paint-studio/cmd/studio/main.go`
  - Studio Done event, unpadding, preview setting, and library save.
- `research/fh6-paint-studio/cmd/fh6paint/main.go`
  - CLI geometry/preview write path and `RenderFH6` usage.
- `research/fh6-paint-studio/cmd/fh6paint/commands.go`
  - `fh6-score` renders geometry JSON through `RenderFH6`.

## Geometry data semantics

### Type 1 Rectangle

Source-confirmed role:

- `TypeRectangle = 1`
- It is used as the background shape.
- `engine.newRun` writes it as `Data = [0, 0, width, height]`.
- `RenderFH6` does not rasterize this shape through the normal rectangle renderer.
- Instead, if `transparentBG` is false, `RenderFH6` fills the entire canvas with `shapes[0].Color` RGB and alpha `1`.
- `shapes[0].Color[3]` is not used for that opaque background fill.
- If `transparentBG` is true, the background fill is skipped and the canvas starts transparent.

FLO mismatch:

- FLO currently treats Type 1 like a normal drawable rectangle layer.
- For Paint Studio preview compatibility, FLO should treat `shapes[0]` as canvas background, not as a normal shape.

### Type 2 RotatedRectangle

Source-confirmed semantics:

```text
[cx, cy, halfW, halfH, thetaDeg]
```

Evidence:

- `model.KindRectangle`: `P = [cx, cy, halfW, halfH, thetaDeg, _]`
- `Candidate.ToShape` serializes rectangles to `TypeRotatedRectangle` with the first five values.
- `raster.RectBBox` and `raster.RectInside` use `cx/cy`, `halfW/halfH`, and `thetaDeg`.
- `thetaDeg` is degrees, converted with `thetaDeg * pi / 180`.

Rotation formula:

```text
dx = x + 0.5 - cx
dy = y + 0.5 - cy
xr = dx*cos(theta) + dy*sin(theta)
yr = -dx*sin(theta) + dy*cos(theta)
```

Because image coordinates have Y downward, avoid guessing from visual intuition. FLO should match the source formula.

### Type 16 RotatedEllipse

Source-confirmed semantics:

```text
[cx, cy, rx, ry, thetaDeg]
```

Evidence:

- `model.KindEllipse`: `P = [cx, cy, rx, ry, thetaDeg, _]`
- `Candidate.ToShape` default path serializes ellipses to `TypeRotatedEllipse`.
- `raster.EllipseBBox` and `raster.EllipseInside` use `cx/cy`, `rx/ry`, and `thetaDeg`.
- `thetaDeg` is degrees, converted with `thetaDeg * pi / 180`.

FLO mismatch:

- FLO parser currently normalizes Paint Studio ellipse `x/y` to `cx/cy`, but the default preview renderer treats normalized `x/y` as top-left.
- This confirms the suspected center-coordinate conversion bug.

### Type 32 Triangle

Source-confirmed semantics:

```text
[x1, y1, x2, y2, x3, y3]
```

Evidence:

- `model.KindTriangle`: `P = [x1, y1, x2, y2, x3, y3]`
- `Candidate.ToShape` serializes all six triangle point values directly.
- `raster.TriangleBBox` and `raster.TriangleInside` use the three explicit vertices.

FLO mismatch:

- The Paint Studio geometry parser preserves triangle points in `raw`.
- The default FLO preview renderer still renders normalized triangles from a bounding box, which loses exact triangle geometry.

## Color and alpha semantics

Source-confirmed semantics:

- Shape color is stored as RGBA integer bytes: `[R, G, B, A]`.
- RGB bytes are stored as sRGB bytes.
- Alpha is straight alpha.
- Alpha `0` is transparent, alpha `255` is opaque.
- RGB is decoded from sRGB to linear before compositing in `RenderFH6`.
- Alpha is used as `Color[3] / 255`.
- Hard shapes use binary coverage.
- Glow/disk and masks use per-pixel coverage, multiplying effective alpha by coverage.
- Compositing is source-over in linear light:

```text
dst_rgb = dst_rgb * (1 - aEff) + src_rgb * aEff
dst_alpha = dst_alpha * (1 - aEff) + aEff
```

Preview output is converted back to sRGB display floats and saved as straight-alpha NRGBA.

## Layer order semantics

Source-confirmed semantics:

- Geometry is rendered in array order.
- `shapes[0]` is treated as background.
- `RenderFH6` loops from `si := 1` to the end.
- Each later shape is composited over earlier content.
- This means geometry is stored back-to-front.
- `geometry.json` is written with `WriteGeometry` preserving shape order.
- Studio and CLI preview generation do not reverse the list.

## Preview canvas semantics

Source-confirmed behavior:

- Preview canvas size is the prepared generation width/height.
- `imageio.Load` downscales the source so the max side is at most `maxRes`, when maxRes is set.
- Region/crop modes prepare the crop as a separate working canvas.
- `pad-transparent` may enlarge the run canvas, then `TranslateShapes` and `UnpadCanvas` map output back to original dimensions.
- Library preview is the current Studio preview image saved as `preview.png`.
- CLI preview uses `imageio.RenderFH6` and `imageio.SavePreview`.
- Studio final preview uses `imageio.RenderFH6Image`.
- `RenderFH6` supports SSAA when requested by CLI, then box-downsamples in linear light.
- Studio final preview uses SSAA `1`.

Background rule:

- If `transparentBG` is false, the canvas is filled with `shapes[0].Color` RGB at alpha `1`.
- If `transparentBG` is true, the canvas starts transparent.

## FLO mismatch causes

Confirmed or likely FLO assumptions that are wrong:

- Paint Studio rotated rectangle and ellipse data uses center coordinates, but FLO default preview treats normalized `x/y` as top-left.
- Paint Studio triangles use exact three-point geometry, but FLO preview renders triangles from a normalized bounding box.
- Paint Studio preview uses linear-light source-over blending, while FLO preview uses Pillow's RGBA compositing.
- Paint Studio shape 0 is a special background fill, while FLO treats it like a normal layer.
- Paint Studio uses exact raster inside tests at pixel centers; FLO uses Pillow primitives and approximate rotation.
- Paint Studio geometry can be at prepared generation dimensions, which may differ from an external source image if downscaling, crop, or padding was used.

Not strongly supported as root causes:

- RGB/BGR channel swap.
- Blindly reversing layer order.
- Treating all alpha as ignored or inverted.
- Unsupported mask/glyph types for `case_0001`, because its shape types are only `1`, `2`, `16`, and `32`.

## Required FLO changes

### `engine/parser/paint_studio_geometry_parser.py`

Needed later:

- Preserve Paint Studio geometry semantics explicitly in normalized layers, especially `coordinate_mode`.
- Convert center-based geometry to top-left only if the downstream renderer expects top-left.
- Or keep center semantics and teach the renderer to respect `raw`.
- Mark `TypeRectangle` at index 0 as `background`, not a normal rectangle.
- Preserve exact triangle points in a renderer-friendly field, not only in `raw`.

### `engine/renderer/preview_renderer.py`

Needed later:

- Add Paint Studio-aware rendering path.
- Draw Type 2 rectangles using center/half-size/degree rotation.
- Draw Type 16 ellipses using center/radius/degree rotation.
- Draw Type 32 triangles from exact points.
- Treat `shapes[0]` background like Paint Studio `RenderFH6`.
- Use linear-light source-over blending for Paint Studio previews.
- Support optional SSAA.

### Diagnostic scripts

Needed later:

- Add a source-grounded renderer variant that implements `RenderFH6` semantics in Python.
- Compare that variant against Paint Studio `preview.png`.
- Keep current heuristic variants as fallback diagnostics only.

## Do not implement yet

v0.5.8 is audit-only.

Do not:

- implement Anime Cleanup
- output optimized geometry
- change Paint Studio source
- change injection logic
- apply renderer behavior changes until a focused renderer compatibility implementation is started
