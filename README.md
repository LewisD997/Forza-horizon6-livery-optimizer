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

There is still no automatic cleanup or optimized geometry output.

## Renderer Compatibility Diagnostic

Real Paint Studio `geometry.json` files may not yet render faithfully in FLO. If FLO preview is far from Paint Studio preview, visual diff and anime artifact analysis should not be trusted for cleanup decisions.

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
