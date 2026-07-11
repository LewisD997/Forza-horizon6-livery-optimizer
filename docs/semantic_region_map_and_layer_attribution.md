# Semantic Region Map And Layer Attribution

v0.7.0 begins FLO's main visual optimization track. It analyzes the reference image and proposes coarse anime-character regions, then estimates which visible parts of Paint Studio layers contribute to those regions. It does not modify geometry.

## Proposal, Not Perfect Segmentation

The heuristic backend is intentionally conservative. Its labels are `background`, `hair`, `face_skin`, `eyes`, `mouth`, `body_skin`, `clothing`, `foreground_unknown`, plus an auxiliary `outline_edge` mask. Every region has confidence, evidence, provenance, and warnings. Weak evidence remains `foreground_unknown`; eyes and mouth may be absent.

`heuristic_anime_v1` uses meaningful source alpha when available, otherwise border-color separation. It applies deterministic color quantization, connected components, spatial priors, coarse skin/face/hair/eye/mouth/clothing proposals, and exact unknown fallback. It supports optional point and box hints without changing geometry. Light or colored hair is not rejected merely for being non-dark.

## Occlusion-Aware Attribution

A shape center or bounding box cannot tell which pixels remain visible after higher layers cover it. FLO processes shapes from visually topmost to bottommost, rasterizes source-grounded shape alpha, maintains remaining transmittance, and estimates each shape's visible alpha area. Attribution then weights overlap between that visible portion and semantic masks.

Each layer receives a primary region, optional secondary regions, overlap ratios, ambiguity status, occlusion estimate, confidence, and sensitive-region flags. Eyes, face skin, mouth, and outline edges are sensitive. A fully occluded shape is not marked sensitive merely because its original bounds cross an eye.

Region summaries provide initial layer budgets, type distributions, visible/occluded area, cross-region complexity, and optional candidate/action counts. These outputs prepare reference-relative scoring, region-level clustering, and later replacement planning.

## Run

```bash
python scripts/generate_semantic_region_map.py --case cases/case_0001 --backend heuristic-anime --overwrite
python scripts/validate_semantic_region_map.py --regions cases/case_0001/semantic_regions/semantic_regions.json --attribution cases/case_0001/semantic_regions/layer_region_attribution.json --geometry cases/case_0001/paintstudio_geometry.json
```

Optional hints use `semantic_region_hints.json` with positive points, negative points, boxes, and protected labels. Future ML backends can implement the same backend result contract without rewriting layer attribution.

Outputs include semantic JSON, flat-ID map, source overlay, confidence map, review sheet, individual masks, attribution JSON/CSV, region summaries, diagnostics, and a representative attribution overlay.

The heuristic backend is not guaranteed truth. Color similarity, complex backgrounds, unusual crops, effects, and heavy occlusion can reduce confidence. Review the map and unknown ratio before using it as evidence. v0.7.0 writes no cleanup geometry, never overwrites original Paint Studio geometry, and makes no destructive decisions.

## v0.7.0.1 Foreground Correction

Source alpha is now an immutable semantic domain boundary. Alpha-background pixels and their arbitrary RGB values are excluded from clustering, and no morphology, hint, or post-processing step may cross outside source foreground. Strict-alpha validation requires zero transparent leaks, perfect transparent background recall, and exact foreground-domain agreement.

Eye proposals now use per-component and aggregate area, compactness, face overlap, relative position, local contrast, aspect ratio, and at-most-two-candidate guardrails. Uncertain pixels remain face skin or foreground unknown. See `semantic_foreground_guardrails.md`.

## v0.7.0.2 Topology And Alignment

Hard row-band classification has been replaced by a foreground component graph. Face skin derives from a compact face core; hair and clothing propagate from topology and color-continuity seeds. Stripe diagnostics detect broad horizontal transitions.

Layer attribution now audits geometry-to-source alignment, records conservative eye/face-core/mouth sensitive triggers, treats outline as a boundary warning, and generates a dedicated background-attribution review. See `semantic_topology_and_attribution_alignment.md`.
