# Anime Artifact Region Analyzer

The Anime Artifact Region Analyzer is a read-only diagnostic pass for normalized FLO layers.

Its job is to find regions that may look visibly generated instead of cleanly hand-built, especially in anime character liveries.

## Purpose

FLO's updated target is:

```text
high visual similarity + low generated-artifact visibility + clean and sharp anime character output
```

Pixel similarity alone is not enough. A generated livery can match the target image numerically while still looking messy in Forza because it uses obvious circles, soft blobs, tiny patches, or fragmented construction.

This analyzer marks those suspicious regions so future cleanup work can focus on the right local areas.

## What It Detects

The analyzer scans the normalized layer list with a 64x64 grid by default.

It looks for:

- visible round primitive clusters
- ellipse-heavy regions
- groups of tiny layers
- glow/disk use in small-detail areas
- internal-only line geometry
- regions that overlap high visual-difference tiles
- local fragmentation risk
- soft blur/blob risk

Each suspicious region is reported with:

- region bounds
- priority
- artifact score
- round, ellipse, circle, tiny-layer, glow/disk, and line counts
- optional visual diff score
- suspected artifact labels
- a short reason

## Why It Is Read-Only

v0.5.4a only identifies risk. It does not decide what the correct fix should be.

The analyzer does not:

- modify layers
- remove layers
- replace primitives
- write optimized geometry
- touch Paint Studio source
- touch game injection logic

This keeps FLO useful as a diagnostic lab before any cleanup logic exists.

## How It Supports FLO

Anime character outputs need clean silhouettes, readable facial features, sharp hair shapes, and intentional-looking linework.

The analyzer helps separate two different problems:

- visual mismatch from the original image
- visible generated artifacts even when the image is roughly similar

That distinction is important because Anime Cleanup should not chase pixel fitting alone. It should improve the generated solution toward cleaner anime-style construction.

## Known Limitations

- The scoring is heuristic and not a final quality metric.
- It does not understand character semantics such as eyes, hair, mouth, clothing, or highlights.
- It does not inspect actual Paint Studio mask bitmaps.
- `mask_or_unknown` is not treated as automatically bad.
- Preview rendering for glow, disk, and masks is still approximate.
- Region grid boundaries can split one visual artifact across multiple cells.
- It does not know whether a round primitive is intentional or accidental.

## Future Use For Anime Cleanup

Later Anime Cleanup work can use these regions as candidate zones for:

- safer local simplification
- replacing blob-like ellipse clusters
- reducing tiny patch fragmentation
- improving sharp anime edges
- prioritizing cleanup where visual diff is also high
- logging training cases for human review

For now, the analyzer only reports where cleanup may be useful.
