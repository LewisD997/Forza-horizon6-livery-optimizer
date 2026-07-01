# FLO MVP Notes

FLO means Forza Livery Optimizer.

The reference image is the visual target. The generated livery file is the initial solution.

This project does not convert images to SVG. It does not refit a whole image from scratch. It analyzes an existing Paint Studio / Forza Painter style output and reports signs of waste, fragmentation, weak primitive choices, and messy local construction.

## Run

From this folder:

```bash
python main.py --image test_data/original.png --input test_data/generated.jsdn --report output/report.json --preview output/preview.png --diff output/diff.png
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

## MVP Features

- Parses `.jsdn` as JSON first.
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
- Uses a local Forza primitive knowledge base to explain suspicious shape usage and suggest possible replacement primitives.

## Report Shape

```json
{
  "total_layers": 0,
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
  "issues": [],
  "suspected_messy_regions": [],
  "estimated_removable_layers": 0,
  "notes": []
}
```

## Not Included Yet

- No UI.
- No AI.
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
- a plain-language reason

This is only diagnostic. FLO does not rewrite `.jsdn` files yet.

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
