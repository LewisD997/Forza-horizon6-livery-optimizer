# FLO v0.5.2 Paint Studio Integration Audit

## 1. Current Python FLO Verification

- Commit checked: `3d5b7be`
- Branch status before audit edits: `main...origin/main`
- `python -m compileall .`: passed.
- Smoke command: passed.

Smoke command used:

```bash
python main.py --image test_data/original.png --input test_data/generated.jsdn --report output/report.json --preview output/preview.png --diff output/diff.png --log-training-cases
```

Generated outputs:

- `output/report.json`
- `output/preview.png`
- `output/diff.png`
- `database/training_cases.jsonl`

Note: `--log-training-cases` appends to `database/training_cases.jsonl`. That is a smoke-test side effect, not an audit logic change.

## 2. Updated FLO Direction

FLO should optimize anime character outputs for:

```text
high visual similarity + low generated-artifact visibility + clean and sharp appearance
```

FLO should continue using FH6 Paint Studio's existing generation, fitting, preview, library, and injection ecosystem.

FLO's core innovation is not generating layers from scratch. It should improve the generated initial solution.

## 3. Paint Studio Architecture Findings

Important inspected files:

- `internal/model/model.go`: core shape model, output JSON `Shape`, `Geometry`, shape kind/type mapping.
- `internal/model/mask.go`: registered mask-word shape model.
- `internal/engine/run.go`: main generation orchestrator.
- `internal/engine/polish.go`: post-greedy joint polish and shape refinement.
- `internal/runner/runner.go`: UI runner wrapper around `engine.Run` / `engine.GenerateGaussian`.
- `cmd/studio/main.go`: Studio UI event loop, generation completion, library save, edit, export, inject actions.
- `internal/library/library.go`: saved generation library layout and `geometry.json`.
- `internal/imageio/output.go`: geometry JSON read/write and in-game-faithful renderer.
- `internal/inject/layer.go`: conversion from `model.Shape` to live FH6 layer writes.
- `internal/inject/profile.go`: FH6 shape words and memory field offsets.
- `internal/maskbank/maskbank.go`: embedded mask/word registry.
- `internal/maskbank/manifest.json`: registered dictionary shapes.
- `internal/ui/editor_palette.go`: manual editor quick-add primitive palette.
- `internal/ui/editor_bank.go`: mask/glyph/curve/decal bank UI.
- `internal/ui/shapekinds.go`: generator shape selection UI for ellipse, rectangle, triangle.
- `internal/preset/preset.go`: user choices, generation mode resolution, supported generator kind names.

## 4. Shape Model Findings

Paint Studio's final geometry is represented as:

```go
type Shape struct {
    Type   int       `json:"type"`
    Data   []float64 `json:"data"`
    Color  []int     `json:"color"`
    Score  float64   `json:"score"`
    Locked bool      `json:"locked,omitempty"`
}

type Geometry struct {
    Shapes []Shape `json:"shapes"`
}
```

Core candidate shape kinds:

- `KindEllipse`: `P = [cx, cy, rx, ry, thetaDeg, _]`
- `KindRectangle`: `P = [cx, cy, halfW, halfH, thetaDeg, _]`
- `KindTriangle`: `P = [x1, y1, x2, y2, x3, y3]`
- `KindLine`: internal only; no FH6 injectable primitive.
- `KindGlow`: native radial gradient, word `0x00e4`.
- `KindDisk`: native radial disk, word `0x00e2`.
- `KindMaskBase + i`: registered maskbank words.

Output type IDs:

- `TypeRectangle = 1`
- `TypeRotatedRectangle = 2`
- `TypeRotatedEllipse = 16`
- `TypeTriangle = 32`
- `TypeLine = 64`
- `TypeGradGlow = 0xE4`
- `TypeGradDisk = 0xE2`

Output format:

- Saved/generated geometry uses `model.Geometry` JSON:
  `{"shapes":[...]}`
- `shapes[0]` is the background shape.
- Library saves this as `geometry.json`.

## 5. Generation / Polish Hook Point

Generation begins in Studio through:

```text
cmd/studio/main.go -> runner.RunAsync(...) -> engine.Run(...) or engine.GenerateGaussian(...)
```

`engine.Run` orchestrates:

1. `newRun`
2. optional live/glyph prepass
3. greedy placement
4. `postProcess`
5. `refine`

The final shapes are returned as:

```go
engine.Result{Shapes: r.shapes, InitialError: r.initialErr, FinalError: r.finalErr}
```

The safest FLO hook is after generation and polish/refine are complete, before Studio saves to Library or sends shapes to the editor/injector.

Recommended conceptual hook:

```go
shapes = animecleanup.Clean(shapes, sourceImage, settings)
```

Practical candidate location:

- In `cmd/studio/main.go`, inside `case runner.Done`, after:
  - hybrid ink has been appended if enabled
  - crop/unpad translation has been applied
  - `shapes` and `canvas` are final
- Before:
  - `lastShapes = shapes`
  - `saveDecalToLibrary(...)`
  - editor entry or library injection flows

This keeps Paint Studio's generation, preview, library, and injection ecosystem intact.

## 6. Library / Inject Flow

Library save:

```text
cmd/studio/main.go -> saveDecalToLibrary -> library.Store.Save
```

Library format:

- `geometry.json`: importer-compatible `model.Geometry`
- `preview.png`
- `thumb.png`
- `meta.json`

Manual edited designs also save through:

```text
saveEditedDesign -> library.Store.Save
```

Inject flow:

```text
Library row Inject -> store.LoadGeometry -> runInject -> inject.NewFH6 -> inj.Inject
```

`runInject` creates:

```go
cm := inject.NewCanvasMap(w, h, float32(scale), inject.ScaleBase)
inj.Canvas = &cm
inj.Inject(shapes, w, h)
```

`internal/inject/layer.go` converts `model.Shape` into per-layer field writes:

- position
- scale
- rotation
- skew
- color
- mask flag
- shape word

Important safety finding:

The injector deliberately writes the shape word only and never writes the geometry resource pointer at `0xA8`, because doing so can corrupt FH6 layer ownership and crash the game.

## 7. Shape Word and Official Shape Support

Confirmed shape words from `internal/inject/profile.go` and `internal/inject/layer.go`:

- square: `0x0065`
- circle: `0x0066`
- triangle: `0x0068`
- circle border: `0x0070`
- ellipse word: `0x0088`, but documented as rendering like a crescent, not a normal ellipse
- glow: `0x00e4`
- disk: `0x00e2`

Support summary:

| Shape | Generator | Editor | Injector | Notes |
| --- | --- | --- | --- | --- |
| square | generator_supported | editor_supported | injector_supported | Rectangle kind maps to square word `0x0065`. |
| circle | generator_supported | editor_supported | injector_supported | Ellipse with equal radii maps to circle word `0x0066`. |
| ellipse | generator_supported | editor_supported | injector_supported | Uses circle word `0x0066` with non-uniform scale. |
| triangle | generator_supported | editor_supported | injector_supported | Uses word `0x0068`; triangle affine fit is implemented. |
| line | internal_only | editor_supported | not injector_supported | `TypeLine` exists, but no FH6 primitive mapping; injector skips it. |
| glow | generator_supported | editor_supported | injector_supported | Native radial gradient word `0x00e4`; Gaussian mode emits glow splats. |
| disk | known_but_not_emitted | editor_supported | injector_supported | Modeled and editor-addable; normal generator path does not appear to emit it. |
| circle border | known_but_not_emitted | editor_supported | injector_supported | Word `0x0070`; appears in maskbank as `ring-sm_0070`. |
| arc-like shapes | known_but_not_emitted | editor_supported | injector_supported | Present in maskbank as arc/gentlearc entries. |
| crescent-like shapes | known_but_not_emitted | editor_supported | injector_supported | Word `0x0088` behaves like crescent; maskbank has crescent entries. |
| trapezoid-like shapes | unknown | unknown | unknown | No explicit support confirmed in inspected files. |
| glyph / font shapes | known_but_not_emitted | editor_supported | injector_supported | Maskbank letters/glyphs, glyph proposer/prepass exist, but default generation does not emit them. |
| mask shapes | known_but_not_emitted | editor_supported | injector_supported | Mask words register through `maskbank` and serialize as word-type shapes. |

Machine-readable draft:

```text
database/paint_studio_shape_capabilities.json
```

## 8. Candidate FLO Integration Design

Suggested package:

```text
internal/animecleanup
```

Possible API:

```go
func Clean(shapes []model.Shape, source image.Image, settings Settings) ([]model.Shape, Report)
```

Suggested `Settings` fields:

- max allowed visual loss
- circle/ellipse artifact penalty weights
- anime edge sharpness weight
- minimum layer saving threshold
- safe/smart/reconstruction mode toggle
- allow mask/glyph substitutions
- allow gradient primitives

Suggested `Report` fields:

- visual similarity before/after
- layer count before/after
- changed regions
- removed/replaced layer IDs or indices
- artifact penalties
- risk level
- rejected candidate count

The first integration should be read-only/diagnostic inside Studio or run as a post-generation report before mutation.

## 9. Anime Cleanup Scoring Goal

Proposed scoring direction:

```text
final_score =
visual_similarity
- visible_circle_penalty
- visible_ellipse_penalty
- blob_artifact_penalty
+ clean_edge_score
+ anime_clarity_score
```

Interpretation:

- `visual_similarity`: still preserves the original target.
- `visible_circle_penalty`: discourages obvious generated circle stamps in anime faces/hair.
- `visible_ellipse_penalty`: discourages blobby oval artifacts.
- `blob_artifact_penalty`: detects smooth generated blobs that do not read as intentional anime shapes.
- `clean_edge_score`: rewards sharp silhouettes, hair edges, eye lines, and clothing boundaries.
- `anime_clarity_score`: rewards readable character features over raw pixel SSE.

## 10. Risks / Unknowns

Still needs manual testing inside Paint Studio / FH6:

- Whether every maskbank word injects correctly across current FH6 builds.
- Whether crescent/ellipse word behavior is stable in the user's installed build.
- Whether glow/disk words are safe in all templates and reload flows.
- Whether glyph proposer/prepass is reliable enough for anime cleanup or should stay diagnostic.
- Whether line-like output should become mask/arc/stroke substitution instead of `TypeLine`.
- Whether cleanup should run before or after hybrid ink append for anime-ink modes.
- Whether cleanup should alter `geometry.json`, Studio preview, Library preview, or only produce a report at first.
- How to measure anime-specific clarity without overfitting to one style.
- Whether shape replacement affects layer ordering and FH6 editor usability.
- Whether any official shape list exists outside the embedded maskbank manifest and hard-coded shape words.

## 11. Recommended Next Step

Smallest safe implementation step after this audit:

```text
v0.5.3 Paint Studio Shape Registry Adapter Prototype
```

That step should not modify injection logic.

Recommended scope:

1. Create a local adapter in Python or documentation that maps FLO primitive names to Paint Studio `model.Shape` types and shape words.
2. Add test fixtures using exported `geometry.json` from Paint Studio.
3. Confirm FLO can read Paint Studio geometry JSON as an initial solution in addition to `.jsdn`.
4. Keep all output diagnostic-only.

Do not implement Anime Cleanup yet.
