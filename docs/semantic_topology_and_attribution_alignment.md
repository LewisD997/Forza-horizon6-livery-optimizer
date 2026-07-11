# Semantic Topology And Attribution Alignment

v0.7.0.2 removes the most damaging row-band assumptions from FLO's experimental semantic proposal. A horizontal slice is not semantic understanding: long hair can extend below clothing, hands can sit above a face, and garments can wrap around the upper body.

## Component Topology

FLO now splits foreground-only color clusters into connected components and builds a local adjacency graph. Nodes record area, bounds, centroid, mean and median color, cluster identity, foreground-boundary contact, confidence, and candidate labels. Edges record direct or small-gap proximity, color distance, and boundary contact. Tiny noise nodes are suppressed diagnostically rather than classified pixel by pixel.

Position inside the foreground bbox remains a soft seed prior. It is not a hard full-width cutoff. Hair and clothing propagate through graph connectivity and color continuity from head/scalp and torso/garment seeds. Ambiguous components remain foreground unknown.

## Face Core And Skin

`face_core.png` is a conservative compact skin component near the head center, optionally expanded only through small adjacent skin components. `face_skin` derives from this core. Other skin becomes `body_skin`, so hands, arms, chest, and detached skin are not promoted to face merely because they are high on the canvas. Weak face evidence produces no face core.

## Stripe Diagnostics

`semantic_stripe_diagnostics.json` detects broad same-row label transitions, while `semantic_stripe_overlay.png` marks affected rows. Diagnostics explicitly list every spatial threshold as a soft prior or hard constraint. v0.7.0.2 declares no hard horizontal semantic thresholds.

## Sensitive Attribution

Sensitive status now requires meaningful visible overlap with eyes, face core, or mouth. Each trigger records its label, overlap ratio, visible area, threshold, and reason. Outline overlap is retained as `sensitive_boundary` but does not by itself make a shape fully sensitive. Tiny broad face overlap is not sufficient.

## Alignment And Background Review

`semantic_attribution_alignment_audit.json` records source and geometry sizes, transform, alignment method, visible geometry union, geometry on source background, missing source coverage, background-primary count, confidence, and warnings. Identity is used only when source and geometry render dimensions match; otherwise a scale transform and warning are recorded.

Background-primary shapes are listed separately in JSON/CSV and a review sheet. The base shape, fully occluded shapes, and unsupported shapes are excluded. This helps distinguish geometry beyond the alpha silhouette, renderer/alpha differences, attribution thresholds, and coordinate misalignment.

The system remains analysis-only and experimental. Topology and alignment diagnostics improve evidence quality but do not authorize geometry changes or guarantee semantic truth.
