# forza-livery-optimizer

FLO is a command-line Python MVP for inspecting generated Forza livery files.

It treats the original image as the target and the generated `.jsdn` livery as the initial solution. The goal is to move toward cleaner, simpler, more hand-drawn-looking Forza liveries with fewer wasteful layers.

Full notes are in [docs/README.md](docs/README.md).

## Quick Start

For `.jsdn` input:

```bash
python main.py --image test_data/original.png --input test_data/generated.jsdn --input-format jsdn --report output/report.json --preview output/preview.png --diff output/diff.png --log-training-cases
```

For Paint Studio `geometry.json` input:

```bash
python main.py --image test_data/original.png --input test_data/paint_studio_geometry_sample.json --input-format paintstudio --report output/paintstudio_report.json --preview output/paintstudio_preview.png --diff output/paintstudio_diff.png
```

The current MVP reports problems, renders a preview, generates a visual diff, detects anime artifact regions, uses a local primitive knowledge base, and produces ranked optimization suggestions. It can read `.jsdn` and Paint Studio `geometry.json` inputs. It does not delete, rewrite, or optimize the livery file.

Anime artifact diagnostics are reported under:

```text
anime_artifact_analysis
```

## Case-Driven Development

FLO now includes a text-only case library structure under `cases/` and hypothesis-level anime livery rules in:

```text
database/anime_livery_rules.json
```

These rules are not verified yet. They stay at hypothesis level until real anime livery cases, human notes, and region labels provide evidence.

There is still no automatic cleanup and no in-place geometry rewriting.

## Safe Optimized Geometry Output

FLO v0.6.0 can write a separate optimized Paint Studio geometry file in safe noop mode:

```bash
python main.py --image cases/case_0001/source_full.png --input cases/case_0001/paintstudio_geometry.json --input-format paintstudio --report cases/case_0001/flo_report.json --preview cases/case_0001/flo_preview.png --diff cases/case_0001/flo_diff.png --output-geometry cases/case_0001/optimized_geometry.json --optimization-mode noop --after-preview cases/case_0001/optimized_preview.png --after-diff cases/case_0001/optimized_diff.png --preview-renderer paintstudio-source
```

`noop` makes no shape changes. It only proves the safe output pipeline. Validate with:

```bash
python scripts/validate_optimized_geometry.py --input cases/case_0001/paintstudio_geometry.json --output cases/case_0001/optimized_geometry.json
```

## Optimization Plans

FLO v0.6.1 can write a safe optimization plan / patch ledger before any real geometry changes happen:

```bash
python main.py --image cases/case_0001/source_full.png --input cases/case_0001/paintstudio_geometry.json --input-format paintstudio --report cases/case_0001/flo_report.json --output-geometry cases/case_0001/optimized_geometry.json --optimization-mode noop --plan-output cases/case_0001/optimization_plan.json --preview-renderer paintstudio-source
```

Validate a plan:

```bash
python scripts/validate_optimization_plan.py --plan cases/case_0001/optimization_plan.json --geometry cases/case_0001/paintstudio_geometry.json
```

Supported planning flags include `--plan-output`, `--plan-input`, `--apply-plan`, `--dry-run-plan`, and `--include-mark-candidates`.

v0.6.2 adds non-destructive candidate planning:

```bash
python main.py --image cases/case_0001/source_full.png --input cases/case_0001/paintstudio_geometry.json --input-format paintstudio --report cases/case_0001/flo_report.json --output-geometry cases/case_0001/optimized_geometry.json --optimization-mode candidate-plan --plan-output cases/case_0001/optimization_plan.json --preview-renderer paintstudio-source --max-candidates 100
```

Candidate plans only mark future cleanup candidates. They do not delete, update, or add shapes.

Render candidate review images:

```bash
python scripts/render_candidate_review.py --case cases/case_0001 --top-n 50
```

This writes overlays, contact sheets, crops, a CSV table, and a review index under `cases/case_0001/candidate_review/`.

Record human feedback for candidates:

```bash
python scripts/create_candidate_feedback_template.py --case cases/case_0001
python scripts/update_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json --change-id C0001 --status unsure --note "Initial placeholder review"
python scripts/validate_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json --plan cases/case_0001/optimization_plan.json
python scripts/summarize_candidate_feedback.py --feedback cases/case_0001/candidate_review/candidate_feedback.json
```

Feedback statuses are `accepted`, `rejected`, `unsure`, and `protected`. This is review-only and does not modify geometry.

## Renderer Compatibility Diagnostic

Real Paint Studio `geometry.json` files may not yet render faithfully in FLO. If FLO preview is far from Paint Studio preview, visual diff and anime artifact analysis should not be trusted for cleanup decisions.

For source-grounded Paint Studio preview rendering, run:

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 2
```

This creates `source_grounded` preview outputs under the case folder and uses Paint Studio source-confirmed semantics for background, layer order, center-based rectangles/ellipses, triangle vertices, RGBA color, and linear-light alpha blending.

For Paint Studio preview export alignment variants:

```bash
python scripts/render_paintstudio_source_preview.py --case cases/case_0001 --ssaa 4 --run-export-variants
```

This compares full-canvas and cropped transparent exports when a Paint Studio `preview.png` is available, and writes more readable diff images.

Run the renderer diagnostic on a prepared case:

```bash
python scripts/diagnose_paintstudio_renderer.py --case cases/case_0001
```

It writes diagnostic render variants under the case folder without modifying geometry.

Geometry semantics can be inspected with:

```bash
python scripts/debug_paintstudio_geometry_layers.py --case cases/case_0001
```

This creates layer slices, type-isolation renders, and background interpretation tests for debugging Paint Studio `geometry.json` semantics.
