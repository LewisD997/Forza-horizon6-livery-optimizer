# forza-livery-optimizer

FLO is a command-line Python MVP for inspecting generated Forza livery files.

It treats the original image as the target and the generated `.jsdn` livery as the initial solution. The goal is to move toward cleaner, simpler, more hand-drawn-looking Forza liveries with fewer wasteful layers.

Full notes are in [docs/README.md](docs/README.md).

## Quick Start

```bash
python main.py --image test_data/original.png --input test_data/generated.jsdn --report output/report.json
```

The first MVP reports problems only. It does not delete, rewrite, or optimize the livery file.
