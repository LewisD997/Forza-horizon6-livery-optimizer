# FLO Case Library

This folder is for real anime livery case studies.

Do not commit copyrighted source images unless you own the rights or have clear permission.

The case library exists so FLO rules can be grounded in actual examples instead of private assumptions.

## Case Folder Layout

Each case should use its own folder:

```text
cases/
  my_case_id/
    case_manifest.json
    human_notes.md
    regions.json
    source_full.png
    source_face_crop.png
    source_eye_left.png
    source_eye_right.png
    paintstudio_geometry.json
    paintstudio_preview.png
    flo_report.json
    flo_diff.png
    human_fixed_geometry.json
    human_fixed_preview.png
```

Only the text template is included in Git. Real images and exported geometry should be added case by case when the user is ready.

## Files To Place In A Real Case

- `source_full.png`: original reference image.
- `source_face_crop.png`: face crop for anime clarity review.
- `source_eye_left.png`: left eye crop.
- `source_eye_right.png`: right eye crop.
- `paintstudio_geometry.json`: Paint Studio generated geometry.
- `paintstudio_preview.png`: Paint Studio preview render.
- `flo_report.json`: FLO diagnostic report.
- `flo_diff.png`: FLO visual diff output.
- `human_fixed_geometry.json`: optional human-improved geometry.
- `human_fixed_preview.png`: optional human-improved preview.

## Template

Start from:

```text
cases/case_template/
```

Copy that folder, rename it, and replace the template notes with real observations.
