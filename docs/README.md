# FLO MVP Notes

FLO means Forza Livery Optimizer.

The reference image is the visual target. The generated livery file is the initial solution.

This project does not convert images to SVG. It does not refit a whole image from scratch. It analyzes an existing Paint Studio / Forza Painter style output and reports signs of waste, fragmentation, weak primitive choices, and messy local construction.

## Run

From this folder:

For `.jsdn` input:

```bash
python main.py --image test_data/original.png --input test_data/generated.jsdn --input-format jsdn --report output/report.json --preview output/preview.png --diff output/diff.png --log-training-cases
```

For Paint Studio `geometry.json` input:

```bash
python main.py --image test_data/original.png --input test_data/paint_studio_geometry_sample.json --input-format paintstudio --report output/paintstudio_report.json --preview output/paintstudio_preview.png --diff output/paintstudio_diff.png
```

The report is written to:

```text
output/report.json
```

The preview is written to:

```text
output/preview.png
```

The visual diff is written to:

```text
output/diff.png
```

Pending training cases are appended to:

```text
database/training_cases.jsonl
```

## MVP Features

- Parses `.jsdn` as JSON first.
- Parses Paint Studio `geometry.json` files when `--input-format paintstudio` is used, or when auto-detection sees a top-level Paint Studio `shapes` list.
- Normalizes each layer into a stable structure.
- Loads the original image and extracts:
  - image size
  - dominant colors
  - edge density
  - high-detail regions placeholder
- Detects:
  - duplicate layers
  - very small layers
  - extremely stretched layers
  - nearly identical colors
  - suspicious edge-fixing fragments
  - messy clusters of many small layers in one area
- Renders a basic PNG preview of the generated layer stack when `--preview` is provided.
- Preview rendering currently supports approximate rectangle, square, circle, ellipse, triangle, and line primitives.
- Unknown shape types are drawn as semi-transparent debug bounding boxes and noted in the report.
- Compares the original image against the rendered preview when `--diff` is provided.
- Reports a global visual difference score and high-difference grid regions.
- Reports simple cleanliness, fragmentation, and layer efficiency scores.
- Reports `anime_artifact_analysis` for suspicious anime-generated artifact regions such as visible round primitive clusters, tiny layer fragmentation, glow/disk blob risk, and internal-only line warnings.
- Uses a local Forza primitive knowledge base to explain suspicious shape usage and suggest possible replacement primitives.
- Provides a case-driven development structure so future anime livery rules can be backed by real cases instead of assumptions.
- Generates ranked optimization suggestions without modifying `.jsdn`.
- Can log pending suggestion cases for later human review.

## Report Shape

```json
{
  "total_layers": 0,
  "input_format": "jsdn",
  "image_info": {},
  "preview_path": null,
  "visual_diff": {
    "diff_path": null,
    "global_difference_score": 0,
    "high_difference_regions": []
  },
  "scores": {
    "cleanliness_score": 0,
    "fragmentation_score": 0,
    "layer_efficiency_score": 0
  },
  "unknown_primitives": [],
  "anime_artifact_analysis": {
    "summary": {
      "artifact_region_count": 0,
      "high_priority_region_count": 0,
      "visible_round_primitive_count": 0,
      "ellipse_cluster_count": 0,
      "soft_blur_risk_count": 0,
      "fragmentation_risk_count": 0,
      "line_internal_only_count": 0,
      "overall_anime_artifact_score": 0
    },
    "regions": [],
    "notes": []
  },
  "optimization_suggestions": [],
  "suggestion_summary": {
    "total_suggestions": 0,
    "safe": 0,
    "smart": 0,
    "reconstruction": 0,
    "estimated_total_layer_saving": 0
  },
  "issues": [],
  "suspected_messy_regions": [],
  "estimated_removable_layers": 0,
  "notes": []
}
```

## Not Included Yet

- No UI.
- No AI.
- No model training.
- No destructive optimization.
- No automatic layer rewriting.

## Primitive Knowledge Base

FLO keeps a local primitive knowledge base at:

```text
database/forza_primitives.json
```

It describes common normalized primitives such as rectangle, circle, triangle, line, arc, crescent, trapezoid, polygon, and unknown. Analyzer issues can use this data to add:

- current primitive
- visual traits
- possible replacement primitives
- a plain-language primitive reason

Shapes not found in the knowledge base are listed in `unknown_primitives` in the report.

This is only diagnostic. FLO does not rewrite `.jsdn` files yet.

## Optimization Suggestions

FLO can generate ranked suggestions in three modes:

- `safe`: likely removable or redundant layers, such as duplicates or tiny invisible details.
- `smart`: primitive substitutions or cleanup ideas, such as line replacement, arc replacement, or near-identical color merges.
- `reconstruction`: local rebuild candidates for messy clusters or high-difference regions.

Suggestions are advisory only. FLO does not automatically edit the livery file.

## Anime Artifact Analysis

FLO reports anime-specific artifact risk under:

```text
anime_artifact_analysis
```

This pass scans normalized layers in grid regions and flags local signs of generated-looking output:

- visible round/blob primitive clusters
- ellipse-heavy regions
- tiny layer fragmentation
- glow/disk soft blur risk
- internal-only line geometry
- overlap with high visual-difference regions

It supports FLO's goal of high visual similarity with lower generated-artifact visibility and cleaner, sharper anime character output.

Full notes:

```text
docs/anime_artifact_region_analyzer.md
```

## Case-Driven Development

FLO keeps a text-only case library template under:

```text
cases/
```

Starter anime livery rules live in:

```text
database/anime_livery_rules.json
```

All current rules are hypothesis-level only:

- `confidence`: `hypothesis`
- `evidence_level`: `0`
- `evidence_cases`: `[]`

Real cases should include source images, Paint Studio geometry, previews, FLO reports, region labels, and human notes. The template explains where to place those files, but no copyrighted images or placeholder binaries are included.

Case schema:

```text
docs/case_library_schema.md
```

Development direction:

```text
docs/flo_case_driven_development.md
```

Validation:

```bash
python scripts/validate_case_library.py
```

This is still diagnostic-only. FLO does not automatically clean up or rewrite geometry.

## Training Cases

Use `--log-training-cases` to append pending review cases to:

```text
database/training_cases.jsonl
```

Each case starts with `user_decision` set to `pending`.

## Dependencies

The analyzer can read the included sample PNG with the Python standard library.

Preview rendering requires Pillow:

```bash
pip install pillow
```

## Unknown `.jsdn` Formats

If FLO cannot parse the file as JSON, it saves a readable debug dump next to the input file under:

```text
test_data/debug/
```

That dump is meant to help inspect real exported formats later.

## Paint Studio Geometry Input

Paint Studio stores generated designs as `geometry.json` with a top-level `shapes` list. FLO v0.5.3 can read that file as an initial solution:

```bash
python main.py --image test_data/original.png --input path/to/geometry.json --input-format paintstudio --report output/paintstudio_report.json --preview output/paintstudio_preview.png --diff output/paintstudio_diff.png
```

Supported Paint Studio types are documented in:

```text
docs/paint_studio_geometry_adapter.md
```
