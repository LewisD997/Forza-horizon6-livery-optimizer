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

## Safe Optimized Geometry Output

FLO v0.6.0 can write a separate Paint Studio `optimized_geometry.json` in safe noop mode:

```bash
python main.py --image cases/case_0001/source_full.png --input cases/case_0001/paintstudio_geometry.json --input-format paintstudio --report cases/case_0001/flo_report.json --preview cases/case_0001/flo_preview.png --diff cases/case_0001/flo_diff.png --output-geometry cases/case_0001/optimized_geometry.json --optimization-mode noop --after-preview cases/case_0001/optimized_preview.png --after-diff cases/case_0001/optimized_diff.png --preview-renderer paintstudio-source
```

Validate the output:

```bash
python scripts/validate_optimized_geometry.py --input cases/case_0001/paintstudio_geometry.json --output cases/case_0001/optimized_geometry.json
```

Noop mode intentionally makes no geometry changes. Full notes:

```text
docs/optimized_geometry_output.md
```

## Optimization Plans

FLO v0.6.1 can write and validate a safe optimization plan / patch ledger:

```bash
python main.py --image cases/case_0001/source_full.png --input cases/case_0001/paintstudio_geometry.json --input-format paintstudio --report cases/case_0001/flo_report.json --output-geometry cases/case_0001/optimized_geometry.json --optimization-mode noop --plan-output cases/case_0001/optimization_plan.json --preview-renderer paintstudio-source
```

Plan validation:

```bash
python scripts/validate_optimization_plan.py --plan cases/case_0001/optimization_plan.json --geometry cases/case_0001/paintstudio_geometry.json
```

CLI flags:

```text
--plan-output
--plan-input
--apply-plan
--dry-run-plan
--include-mark-candidates
```

Full notes:

```text
docs/optimization_plan_and_patch_ledger.md
```

## Non-Destructive Candidate Planner

FLO v0.6.2 can generate review-only cleanup candidates:

```bash
python main.py --image cases/case_0001/source_full.png --input cases/case_0001/paintstudio_geometry.json --input-format paintstudio --report cases/case_0001/flo_report.json --output-geometry cases/case_0001/optimized_geometry.json --optimization-mode candidate-plan --plan-output cases/case_0001/optimization_plan.json --preview-renderer paintstudio-source --max-candidates 100
```

Options:

```text
--max-candidates
--min-candidate-score
--include-low-confidence
```

Test:

```bash
python scripts/test_candidate_planner.py
```

Full notes:

```text
docs/non_destructive_candidate_planner.md
```

## Candidate Review Visualization

FLO v0.6.3 can render review images from `optimization_plan.json`:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --top-n 50
```

It writes candidate overlays, contact sheets, crops, a review CSV, and an index under:

```text
cases/case_0001/candidate_review/
```

Full notes:

```text
docs/candidate_review_visualization.md
```

## Candidate Review Feedback

FLO v0.6.4 can create and validate human feedback for cleanup candidates:

```bash
python scripts/create_candidate_feedback_template.py --case cases/case_0001
python scripts/update_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json --change-id C0001 --status unsure --note "Initial placeholder review"
python scripts/validate_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json --plan cases/case_0001/optimization_plan.json
python scripts/summarize_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json
```

Supported statuses:

- `accepted`
- `rejected`
- `unsure`
- `protected`

When feedback exists, candidate review contact sheets show feedback status and the review index includes feedback counts.

Feedback-aware review rendering:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --show-feedback
python scripts/render_candidate_review.py --case cases/case_0001 --feedback cases/case_0001/candidate_review/candidate_feedback.json
python scripts/render_candidate_review.py --case cases/case_0001 --feedback-status unsure
```

This writes:

```text
candidate_overlay_feedback_*.png
candidate_contact_sheet_feedback_*.png
candidate_review_feedback_table.csv
```

Full notes:

```text
docs/candidate_review_feedback.md
docs/feedback_aware_review_visualization.md
```

## Accepted Candidate Sandbox Removal

FLO v0.6.6 can simulate removing only accepted candidates from a sandbox geometry copy:

```bash
python scripts/simulate_accepted_removal.py --case cases/case_0001
python scripts/validate_removal_simulation.py --report cases/case_0001/removal_simulation/removal_simulation_report.json --geometry cases/case_0001/paintstudio_geometry.json
```

The simulator writes to:

```text
cases/case_0001/removal_simulation/
```

It blocks protected, rejected, and unsure candidates. It does not modify original geometry, update shape data, add replacement shapes, or touch injection logic.

Full notes:

```text
docs/accepted_candidate_sandbox_removal.md
```

## Renderer Compatibility Diagnostic

Real Paint Studio `geometry.json` files may not yet render faithfully in FLO's preview renderer.

If Paint Studio preview looks good but FLO preview looks wrong, treat the case as renderer compatibility debugging first. Do not trust visual diff, anime artifact analysis, or cleanup evidence until FLO preview roughly matches Paint Studio preview.

Source-grounded Paint Studio renderer:

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 2
```

This renderer reads Paint Studio `geometry.json` directly and applies the source-confirmed background, layer order, Type 2, Type 16, Type 32, RGBA, and linear-light blending rules.

Full notes:

```text
docs/paint_studio_source_renderer.md
```

Export alignment variants:

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 4 --run-export-variants
```

This writes full-canvas, transparent, cropped, and padded cropped render variants plus human-friendly diff images when a Paint Studio preview is available.

Export alignment notes:

```text
docs/paint_studio_preview_export_alignment.md
```

Run:

```bash
python scripts/diagnose_paintstudio_renderer.py --case cases/case_0001
```

The script creates render variants and difference scores under:

```text
cases/case_0001/renderer_diagnostic/
```

Full notes:

```text
docs/paint_studio_renderer_compatibility_debugging.md
```

Geometry semantics audit:

```bash
python scripts/debug_paintstudio_geometry_layers.py --case cases/case_0001
```

This writes layer slices, type-isolation renders, and background interpretation tests under:

```text
cases/case_0001/geometry_debug/
```

Full notes:

```text
docs/paint_studio_geometry_semantics_audit.md
```

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
