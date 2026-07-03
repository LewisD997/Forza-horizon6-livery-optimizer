# FLO Case-Driven Development

FLO should not build human livery drawing logic from assumptions alone.

v0.5.5 introduces a case-driven workflow so future anime cleanup rules can be tied to real examples, human observations, and region labels.

## Core Direction

Paint Studio output remains the initial solution.

FLO should inspect that output and move toward:

```text
high visual similarity + low generated-artifact visibility + clean and sharp anime character output
```

The goal is not to generate layers from scratch.

## Why Case-Driven

Anime cleanup depends on context.

An ellipse may be good in an iris, bad on a hair tip, and acceptable in a soft clothing shadow. Without real cases, FLO would risk hard-coding rules that only sound reasonable.

The case library gives each future rule a place to earn trust.

## Evidence Sources

Each case can connect:

- original source image
- Paint Studio `geometry.json`
- Paint Studio preview
- FLO report
- FLO diff image
- manually labeled regions
- human notes
- optional human-fixed geometry and preview

The combination lets FLO ask a better question:

Did this rule actually help this anime livery region?

## Future Uses

Future versions can use real cases to build:

- eye region analyzer
- hair and face outline artifact analyzers
- cleanup candidate planner
- candidate scoring
- rule evidence upgrades
- feedback dataset for human review

## Current Boundary

v0.5.5 does not implement Anime Cleanup.

It does not:

- modify geometry
- output optimized geometry
- touch Paint Studio source
- touch game injection logic
- add AI
- train models

It only creates the structure needed to collect grounded evidence.
