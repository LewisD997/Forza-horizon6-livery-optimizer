# forza-livery-optimizer

FLO is a command-line Python MVP for inspecting generated Forza livery files.

It treats the original image as the target and the generated `.jsdn` livery as the initial solution. The goal is to move toward cleaner, simpler, more hand-drawn-looking Forza liveries with fewer wasteful layers.

Full notes are in [docs/README.md](docs/README.md).

## Quick Start

```bash
python main.py --image test_data/original.png --input test_data/generated.jsdn --report output/report.json --preview output/preview.png --diff output/diff.png
```

The current MVP reports problems, renders a preview, generates a visual diff, and uses a local primitive knowledge base for diagnostic suggestions. It does not delete, rewrite, or optimize the livery file.
