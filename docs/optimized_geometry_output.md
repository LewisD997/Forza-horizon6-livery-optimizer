# Optimized Geometry Output

v0.6.0 adds the first safe optimized geometry output scaffold.

This version does not perform real cleanup yet. The only supported optimization mode is:

```text
noop
```

Noop mode intentionally makes no shape changes. It exists so FLO can safely prove the output pipeline before any destructive or semi-destructive optimizer is added.

## Safety Rules

- The original Paint Studio geometry file is never overwritten.
- `optimized_geometry.json` is written as a separate file.
- Existing output files are refused unless `--overwrite-output` is passed.
- Shape order is preserved.
- Shape `type`, `data`, `color`, `score`, and `locked` fields are preserved.
- FLO metadata is written to a separate optimization report instead of being inserted into geometry JSON.

## Run

```bash
python main.py --image cases/case_0001/source_full.png --input cases/case_0001/paintstudio_geometry.json --input-format paintstudio --report cases/case_0001/flo_report.json --preview cases/case_0001/flo_preview.png --diff cases/case_0001/flo_diff.png --output-geometry cases/case_0001/optimized_geometry.json --optimization-mode noop --after-preview cases/case_0001/optimized_preview.png --after-diff cases/case_0001/optimized_diff.png --preview-renderer paintstudio-source
```

This writes:

```text
cases/case_0001/optimized_geometry.json
cases/case_0001/optimized_geometry_optimization_report.json
cases/case_0001/optimized_preview.png
cases/case_0001/optimized_diff.png
```

The case folder remains ignored and must not be committed.

## Validate

```bash
python scripts/validate_optimized_geometry.py --input cases/case_0001/paintstudio_geometry.json --output cases/case_0001/optimized_geometry.json
```

The validator checks:

- output file exists
- output JSON is valid
- shape fields are present
- input and output paths are different
- noop output shape count equals input shape count
- known shape fields were not unexpectedly changed
- input file is not modified during validation

## Why This Comes Before Real Cleanup

Before FLO deletes, merges, or reconstructs any Paint Studio shapes, it needs a boring but reliable output path. v0.6.0 builds that path first: read geometry, produce a separate output geometry, render after-preview, write metadata, and validate that noop output is structurally safe.

Future versions can plug real cleanup into this pipeline without changing the basic safety contract.
