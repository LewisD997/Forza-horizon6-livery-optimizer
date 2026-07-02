# FLO Project Checkpoint v0.5

## Current Local Version

The local FLO project has reached v0.5.

Current local support includes:

- Parsing generated `.jsdn` files as the initial Paint Studio / Forza Painter solution.
- Normalizing generated layers into a stable layer structure.
- Inspecting the original reference image for size, dominant colors, edge density, and placeholder high-detail regions.
- Rendering the normalized layer stack into `output/preview.png`.
- Comparing the rendered preview against the original image and writing `output/diff.png`.
- Reporting global visual difference and high-difference regions.
- Detecting duplicate layers, tiny layers, extreme stretch, near-identical colors, edge-fixing fragments, and messy small-layer clusters.
- Using a local Forza primitive knowledge base for diagnostic primitive traits and replacement suggestions.
- Producing ranked optimization suggestions without modifying `.jsdn`.
- Logging pending suggestion review cases to `database/training_cases.jsonl`.
- Running the full test command through `scripts/run_test.bat`.

## Public GitHub Version

The public GitHub repository currently appears to contain only the early MVP state at commit:

```text
91c306a Initial CLI diagnostic MVP with JSDN parser, image inspector, layer analyzer, and JSON report output.
```

The remote `origin/main` currently points to:

```text
91c306abc4aa4e5deab6f602688aff2e5136f615
```

That remote version contains the early parser, analyzer, image inspector, report output, sample data, and initial renderer placeholder files. It does not contain the later local v0.2-v0.5 modules.

## Sync Status

Local `main` is ahead of `origin/main` by 5 commits.

Unpushed local commits:

```text
84d5553 Add optimization suggestion engine
97951b0 Patch primitive knowledge base audit requirements
9983578 Add local Forza primitive knowledge base
b5a06ce Add visual diff analysis and region scoring
42e1f0f Add basic preview renderer
```

The local working tree was clean at the time of this checkpoint before creating this document.

Sync plan:

1. Commit this checkpoint document.
2. Push local `main` to `origin main`.
3. Confirm GitHub shows the v0.5 files and latest commit.
4. Optionally create a tag after the remote is synced, such as `v0.5-diagnostic-suggestion-engine`.

No files should be rewritten for the sync. The local v0.5 work should be pushed as-is.

## Existing Modules

### Parser

The parser lives in:

```text
engine/parser/jsdn_parser.py
```

It attempts to load `.jsdn` as JSON, finds layer lists in common locations, and normalizes each generated layer into the FLO layer schema.

### Renderer

The preview renderer lives in:

```text
engine/renderer/preview_renderer.py
```

It uses Pillow to render normalized layers into a PNG preview. It supports approximate rectangle, square, circle, ellipse, triangle, and line primitives. Unknown shapes are drawn as debug bounding boxes.

### Visual Diff

The visual diff module lives in:

```text
engine/vision/visual_diff.py
```

It compares the original reference image against the rendered preview, writes a diff PNG, calculates a global difference score, and reports high-difference regions.

### Analyzer

The analyzer lives in:

```text
engine/analyzer/layer_analyzer.py
```

It detects suspicious layer patterns such as duplicate layers, tiny details, extreme stretch, near-identical colors, edge-fixing fragments, and messy local clusters. It also calculates diagnostic cleanliness, fragmentation, and layer efficiency scores.

### Primitive Knowledge Base

The primitive knowledge base lives in:

```text
database/forza_primitives.json
engine/knowledge/primitive_kb.py
```

It describes primitives by visual language, including hard edges, soft curves, strokes, fills, sharp tips, round details, large blocks, and small details. Analyzer issues use this knowledge to include primitive traits, possible replacements, and primitive reasoning.

### Suggestion Engine

The suggestion engine lives in:

```text
engine/optimizer/suggestion_engine.py
```

It generates ranked optimization suggestions in three modes:

- `safe`
- `smart`
- `reconstruction`

Suggestions are advisory only. They do not modify `.jsdn`.

### Training Case Logger

The training case logger lives in:

```text
engine/reports/training_case_logger.py
```

When `--log-training-cases` is enabled, it writes pending review cases to:

```text
database/training_cases.jsonl
```

Each case starts with:

```text
user_decision: pending
```

## New Direction

FLO should continue using Paint Studio's generation, fitting, and import ecosystem.

FLO's core innovation is not generating layers from scratch.

FLO changes the optimization target from pure pixel fitting to:

```text
high visual similarity + low generated-artifact visibility + clean and sharp anime character output
```

The goal is still to use the original reference image as the visual target and the Paint Studio generated `.jsdn` as the initial solution.

## Strategic Shift

The standalone Python FLO is now an algorithm prototype and diagnostic lab.

The long-term product direction is to integrate FLO as an Anime Cleanup / Optimization module inside or alongside FH6 Paint Studio.

The Python project should continue to prove algorithms, diagnostics, scoring, primitive knowledge, and review workflows before deeper integration work.

## Immediate Next Step

Recommended next step after sync:

```text
v0.5.2 Paint Studio Integration and Shape Registry Audit
```

Do not implement that audit yet.

The immediate priority is to sync the local v0.5 state to GitHub, then inspect Paint Studio's shape registry, primitive model, import/export assumptions, and integration boundaries.
