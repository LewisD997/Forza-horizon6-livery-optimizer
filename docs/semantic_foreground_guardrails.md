# Semantic Foreground Guardrails

v0.7.0.1 corrects a real-case alpha leakage regression. The first semantic implementation treated most transparent pixels in `case_0001` as foreground because it fell back to border RGB separation. Transparent pixels still carry arbitrary RGB values, often black, and those values are not valid visual evidence. They entered color clustering and produced false hair, clothing, eye, and layer-attribution regions.

## Strict Alpha Domain

When source alpha contains both background and foreground values, FLO uses `source_alpha_strict`. With the default threshold of zero, alpha 0 is background and alpha 1-255 is foreground. This source-derived mask is immutable: semantic proposals, components, morphology, hints, conflict resolution, outline masks, confidence propagation, and unknown fallback are all intersected with it.

Transparent RGB values are excluded before deterministic color quantization. Cluster totals must equal the strict foreground pixel count and clustered background count must remain zero. Hole filling and dilation cannot add a pixel outside the domain.

The strict invariants are:

- transparent semantic leak count is zero
- semantic pixels outside foreground are zero
- transparent background recall is 1.0
- foreground domain match ratio is 1.0
- background count equals source alpha-background count
- every foreground-domain pixel receives exactly one exclusive foreground label

Any violation fails validation. Fully opaque images have no alpha partition and conservatively fall back to border-color foreground extraction; strict-alpha equality rules do not apply to that mode.

## Eye Guardrails

Eye proposals are searched only inside a confident face and face-relative eye band. Components must be compact, sufficiently contrasting, within area/aspect/bbox limits, and small relative to the face. Aggregate selection keeps at most two strongest candidates and caps total eye area. One valid visible eye is allowed. Weak or oversized evidence produces no eye label instead of forcing one.

`semantic_alpha_guardrail.png` renders valid foreground in gray, background in dark color, and any illegal leak in bright warning red. A correct strict-alpha output has no red pixels. The review sheet includes this view, foreground/background counts, unknown ratio, eye ratio, and warnings.

These guardrails establish domain correctness, not semantic truth. Hair, face, eyes, and clothing remain experimental proposals and still require visual review.

v0.7.0.2 builds on this immutable alpha domain with component topology. Graph propagation and alignment auditing do not relax any strict-alpha invariant.
