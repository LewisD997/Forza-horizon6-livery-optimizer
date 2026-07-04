import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.renderer.export_alignment import compare_images, get_alpha_bbox
from engine.renderer.paint_studio_source_renderer import render_paint_studio_preview


EXPORT_MODES = (
    "full_canvas_opaque",
    "full_canvas_transparent",
    "cropped_transparent",
    "cropped_transparent_with_padding",
)


def main():
    parser = argparse.ArgumentParser(
        description="Render a Paint Studio geometry.json preview using source-confirmed semantics."
    )
    parser.add_argument("--case", required=True, help="Case folder, for example cases/case_0001.")
    parser.add_argument("--ssaa", type=int, default=2, choices=(1, 2, 4), help="SSAA scale.")
    parser.add_argument("--export-mode", choices=EXPORT_MODES, default="full_canvas_opaque")
    parser.add_argument("--padding", type=int, default=0, help="Padding for cropped_transparent_with_padding.")
    parser.add_argument("--compare-preview", action="store_true", help="Require comparison metadata for Paint Studio preview when available.")
    parser.add_argument("--make-side-by-side", action="store_true", help="Write a side-by-side comparison image.")
    parser.add_argument("--run-export-variants", action="store_true", help="Render common export alignment variants.")
    args = parser.parse_args()

    try:
        if args.run_export_variants:
            report = run_export_variants(Path(args.case), args.ssaa)
            print(f"Export alignment report written to {report['report_path']}")
            best = report.get("best_variant_by_difference_score")
            if best:
                print(f"Best variant: {best['variant']} ({best['difference_score']})")
        else:
            report = render_case(
                Path(args.case),
                ssaa=args.ssaa,
                export_mode=args.export_mode,
                padding=args.padding,
                compare_preview=args.compare_preview,
                make_side_by_side=args.make_side_by_side,
            )
            print(f"Source-grounded preview written to {report['outputs']['preview']}")
            print(f"Report written to {report['outputs']['report']}")
            if report["comparisons"].get("paintstudio_preview", {}).get("available"):
                score = report["comparisons"]["paintstudio_preview"].get("difference_score")
                print(f"Paint Studio preview difference score: {score}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def render_case(
    case_dir: Path,
    ssaa: int,
    export_mode: str = "full_canvas_opaque",
    padding: int = 0,
    compare_preview: bool = False,
    make_side_by_side: bool = False,
) -> dict:
    paths = _case_paths(case_dir)
    if not paths["geometry"].exists():
        raise FileNotFoundError(f"Missing geometry file: {paths['geometry']}")

    width, height = _source_size(paths["source"])
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    metadata = render_paint_studio_preview(
        str(paths["geometry"]),
        str(paths["preview"]),
        width=width,
        height=height,
        ssaa=ssaa,
        export_mode=export_mode,
        padding=padding,
    )

    diff_outputs = {}
    paintstudio_comparison = _compare_target(
        paths["preview"],
        paths["paintstudio_preview"],
        paths["diff_dir"],
        make_side_by_side=make_side_by_side,
    )
    if paintstudio_comparison.get("diff_outputs"):
        diff_outputs.update(paintstudio_comparison["diff_outputs"])
        _copy_if_present(diff_outputs.get("rgb_residual"), paths["legacy_diff"])
        _copy_if_present(diff_outputs.get("side_by_side"), paths["side_by_side"])

    source_comparison = compare_images(paths["preview"], paths["source"]) if paths["source"].exists() else _missing(paths["source"])

    warnings = list(metadata.get("warnings", []))
    if compare_preview and not paths["paintstudio_preview"].exists():
        warnings.append("Paint Studio preview was requested for comparison but paintstudio_preview.png is missing.")
    if paths["source"].exists() and paths["paintstudio_preview"].exists():
        source_size = _image_size(paths["source"])
        preview_size = _image_size(paths["paintstudio_preview"])
        if source_size != preview_size:
            warnings.append(
                "Paint Studio preview dimensions do not match source_full.png; comparison may require alignment."
            )

    report = {
        "case_dir": str(case_dir),
        "export_mode": export_mode,
        "padding": padding,
        "inputs": {
            "geometry": str(paths["geometry"]),
            "source_full": str(paths["source"]) if paths["source"].exists() else None,
            "paintstudio_preview": str(paths["paintstudio_preview"])
            if paths["paintstudio_preview"].exists()
            else None,
        },
        "outputs": {
            "preview": str(paths["preview"]),
            "diff": str(paths["legacy_diff"]) if paths["legacy_diff"].exists() else None,
            "side_by_side": str(paths["side_by_side"]) if paths["side_by_side"].exists() else None,
            "report": str(paths["report"]),
            "diff_dir": str(paths["diff_dir"]),
        },
        "render_metadata": metadata,
        "comparisons": {
            "paintstudio_preview": paintstudio_comparison,
            "source_full": source_comparison,
        },
        "warnings": warnings,
    }
    paths["report"].write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run_export_variants(case_dir: Path, ssaa: int) -> dict:
    paths = _case_paths(case_dir)
    variant_dir = paths["output_dir"] / "export_variants"
    variant_dir.mkdir(parents=True, exist_ok=True)
    variants = [
        ("full_canvas_opaque", "full_canvas_opaque", 0),
        ("full_canvas_transparent", "full_canvas_transparent", 0),
        ("cropped_transparent", "cropped_transparent", 0),
        ("cropped_transparent_padding_0", "cropped_transparent_with_padding", 0),
        ("cropped_transparent_padding_4", "cropped_transparent_with_padding", 4),
        ("cropped_transparent_padding_8", "cropped_transparent_with_padding", 8),
        ("cropped_transparent_padding_16", "cropped_transparent_with_padding", 16),
    ]
    width, height = _source_size(paths["source"])
    results = []
    for variant_name, mode, padding in variants:
        output_path = variant_dir / f"{variant_name}.png"
        metadata = render_paint_studio_preview(
            str(paths["geometry"]),
            str(output_path),
            width=width,
            height=height,
            ssaa=ssaa,
            export_mode=mode,
            padding=padding,
        )
        paintstudio_comparison = (
            compare_images(output_path, paths["paintstudio_preview"])
            if paths["paintstudio_preview"].exists()
            else _missing(paths["paintstudio_preview"])
        )
        source_comparison = (
            compare_images(output_path, paths["source"])
            if paths["source"].exists() and mode == "full_canvas_opaque"
            else _source_note(paths["source"])
        )
        results.append(
            {
                "variant": variant_name,
                "export_mode": mode,
                "padding": padding,
                "path": str(output_path),
                "output_size": metadata["output_size"],
                "alpha_bbox": metadata["alpha_bbox"],
                "paintstudio_preview": paintstudio_comparison,
                "source_full": source_comparison,
                "warnings": metadata.get("warnings", []),
            }
        )

    report = {
        "case_dir": str(case_dir),
        "ssaa": ssaa,
        "variants": results,
        "best_variant_by_direct_size_match": _best_direct_size_match(results),
        "best_variant_by_difference_score": _best_difference_score(results),
        "best_human_review_candidate": _best_human_review_candidate(results),
        "report_path": str(paths["output_dir"] / "export_alignment_report.json"),
        "notes": [
            "Size-matched comparisons are more reliable than resized comparisons.",
            "Transparent cropped exports are experimental alignment candidates for Paint Studio library previews.",
        ],
    }
    Path(report["report_path"]).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _case_paths(case_dir):
    output_dir = case_dir / "source_renderer"
    return {
        "case_dir": case_dir,
        "geometry": case_dir / "paintstudio_geometry.json",
        "source": case_dir / "source_full.png",
        "paintstudio_preview": case_dir / "paintstudio_preview.png",
        "output_dir": output_dir,
        "preview": output_dir / "paintstudio_source_renderer_preview.png",
        "legacy_diff": output_dir / "paintstudio_source_renderer_diff.png",
        "side_by_side": output_dir / "paintstudio_source_renderer_side_by_side.png",
        "report": output_dir / "paintstudio_source_renderer_report.json",
        "diff_dir": output_dir / "diffs",
    }


def _compare_target(candidate_path, target_path, diff_dir, make_side_by_side=False):
    if not target_path.exists():
        return _missing(target_path)
    return compare_images(
        candidate_path,
        target_path,
        diff_dir=diff_dir,
        prefix="diff",
        make_side_by_side=make_side_by_side,
    )


def _source_size(path):
    if not path.exists():
        return None, None
    return _image_size(path)


def _image_size(path):
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _copy_if_present(source, destination):
    if source and Path(source).exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _missing(path):
    return {
        "available": False,
        "target_path": str(path),
        "difference_score": None,
        "resized_for_score": False,
        "diff_outputs": {},
    }


def _source_note(path):
    return {
        "available": path.exists(),
        "target_path": str(path),
        "difference_score": None,
        "resized_for_score": None,
        "note": "Source comparison is only reported for full_canvas_opaque in export variant runs.",
    }


def _best_direct_size_match(results):
    matches = [
        result
        for result in results
        if result["paintstudio_preview"].get("available")
        and result["paintstudio_preview"].get("dimensions_match")
    ]
    if not matches:
        return None
    return _compact_variant(min(matches, key=lambda item: item["paintstudio_preview"]["difference_score"]))


def _best_difference_score(results):
    scored = [
        result
        for result in results
        if result["paintstudio_preview"].get("available")
        and result["paintstudio_preview"].get("difference_score") is not None
    ]
    if not scored:
        return None
    return _compact_variant(min(scored, key=lambda item: item["paintstudio_preview"]["difference_score"]))


def _best_human_review_candidate(results):
    direct = _best_direct_size_match(results)
    if direct:
        return direct
    return _best_difference_score(results)


def _compact_variant(result):
    comparison = result["paintstudio_preview"]
    return {
        "variant": result["variant"],
        "path": result["path"],
        "output_size": result["output_size"],
        "difference_score": comparison.get("difference_score"),
        "resized_for_score": comparison.get("resized_for_score"),
        "dimensions_match": comparison.get("dimensions_match"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
