# FLO Case Library Schema

FLO needs real cases because anime cleanup rules should not be designed behind closed doors.

The case library records source images, Paint Studio output, FLO diagnostics, manual region labels, and human notes. Future rules can then move from rough hypotheses to evidence-backed behavior.

## Why Real Cases Matter

Anime character liveries depend on readable eyes, sharp hair, clean face outlines, and intentional-looking shadows.

A rule that sounds good in isolation may fail on a real character. The case library makes rule design traceable:

- what image was tested
- what Paint Studio generated
- what FLO detected
- what a human thought was wrong
- which region supports or rejects a rule

## Case Folder Files

Each real case should live in its own folder under `cases/`.

Expected files:

- `case_manifest.json`
- `human_notes.md`
- `regions.json`
- `source_full.png`
- `source_face_crop.png`
- `source_eye_left.png`
- `source_eye_right.png`
- `paintstudio_geometry.json`
- `paintstudio_preview.png`
- `flo_report.json`
- `flo_diff.png`
- optional `human_fixed_geometry.json`
- optional `human_fixed_preview.png`

The template does not include image files. Add real image files only when the user has the right to use them.

## Minimum Case Requirements

A minimal useful case should include:

- `case_manifest.json`
- `human_notes.md`
- `regions.json`
- `source_full.png`
- `paintstudio_geometry.json`
- `paintstudio_preview.png`
- `flo_report.json`
- `flo_diff.png`

## Recommended Case Requirements

A stronger case should also include:

- face crop
- left and right eye crops
- human-fixed geometry, if available
- human-fixed preview, if available
- notes that explicitly mention which rule hypotheses were supported or rejected

## regions.json

`regions.json` stores manually labeled regions in the source image coordinate space.

Example region:

```json
{
  "region_id": "left_eye",
  "region_type": "eye",
  "label": "Left eye",
  "x": 120,
  "y": 90,
  "width": 42,
  "height": 24,
  "notes": "Eyelid got fragmented into tiny layers."
}
```

Important fields:

- `region_id`: stable ID within the case.
- `region_type`: category used to connect evidence to rules.
- `x`, `y`, `width`, `height`: bounding box.
- `notes`: short local observation.

## human_notes.md

Human notes should be plain and direct.

Useful notes include:

- what region looks wrong
- whether the output still reads as the character
- where round blobs are visible
- where tiny layer fragmentation hurts clarity
- where Paint Studio did well
- whether a rule hypothesis is supported or rejected

Avoid turning one opinion into a rule too early. A note is evidence, not a universal law.

## Rule Evidence Levels

Rules start as:

```text
hypothesis
```

Evidence can later move through:

- `hypothesis`: idea only, no real case support.
- `observed_case`: supported by at least one real documented case.
- `user_confirmed`: confirmed by user review or a human cleanup comparison.

Rules should track:

- `evidence_level`
- `evidence_cases`
- `user_confirmed_count`
- `rejected_count`

Rejected evidence matters. If a rule hurts a real case, record that too.
