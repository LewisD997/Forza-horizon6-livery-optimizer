# Template Anime Livery Case

This is a text-only template for a future real anime livery case.

Do not place copyrighted images in this template.

## Expected Files

For a real case, place these files in the copied case folder:

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

## Workflow

1. Export or save Paint Studio geometry as `paintstudio_geometry.json`.
2. Run FLO against the source image and generated geometry.
3. Save FLO outputs as `flo_report.json` and `flo_diff.png`.
4. Manually label important regions in `regions.json`.
5. Write human observations in `human_notes.md`.
6. If a human cleanup exists, add the optional fixed geometry and preview files.
