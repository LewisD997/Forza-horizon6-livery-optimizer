# FLO MVP Notes

FLO means Forza Livery Optimizer.

The reference image is the visual target. The generated livery file is the initial solution.

This project does not convert images to SVG. It does not refit a whole image from scratch. It analyzes an existing Paint Studio / Forza Painter style output and reports signs of waste, fragmentation, weak primitive choices, and messy local construction.

## Run

From this folder:

```bash
python main.py --image test_data/original.png --input test_data/generated.jsdn --report output/report.json
```

The report is written to:

```text
output/report.json
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

## Report Shape

```json
{
  "total_layers": 0,
  "image_info": {},
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
- No actual renderer output yet.
- No automatic layer rewriting.

## Dependencies

The MVP uses only Python standard library modules for the included sample PNG.

If Pillow is installed, FLO will use it for broader image support. Without Pillow, FLO supports simple non-interlaced 8-bit RGB/RGBA PNG files.

## Unknown `.jsdn` Formats

If FLO cannot parse the file as JSON, it saves a readable debug dump next to the input file under:

```text
test_data/debug/
```

That dump is meant to help inspect real exported formats later.
