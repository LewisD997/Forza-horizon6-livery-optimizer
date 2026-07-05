import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.visualization.candidate_review_visualizer import (
    export_candidate_crops,
    render_candidate_contact_sheet,
    render_candidate_overlay,
    write_candidate_review_csv,
    write_candidate_review_index,
    write_review_summary,
)


def main():
    parser = argparse.ArgumentParser(description="Render FLO candidate review overlays and contact sheets.")
    parser.add_argument("--case", help="Case folder, for example cases/case_0001.")
    parser.add_argument("--plan", help="optimization_plan.json path.")
    parser.add_argument("--geometry", help="Paint Studio geometry JSON path.")
    parser.add_argument("--base-image", help="Base image for overlays.")
    parser.add_argument("--output-dir", help="Output candidate_review folder.")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--candidate-type")
    parser.add_argument("--risk-level")
    parser.add_argument("--crop-padding", type=int, default=24)
    parser.add_argument("--no-crops", action="store_true")
    args = parser.parse_args()

    try:
        report = render_review(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Candidate review written to {report['output_dir']}")
    print(f"Total candidates: {report['total_candidates']}")
    print(f"Rendered candidates: {report['rendered_candidates']}")
    return 0


def render_review(args):
    case_dir = Path(args.case) if args.case else None
    plan_path = Path(args.plan) if args.plan else case_dir / "optimization_plan.json"
    geometry_path = Path(args.geometry) if args.geometry else case_dir / "paintstudio_geometry.json"
    output_dir = Path(args.output_dir) if args.output_dir else case_dir / "candidate_review"
    base_image = Path(args.base_image) if args.base_image else _find_base_image(case_dir)

    plan = _load_json(plan_path)
    geometry = _load_json(geometry_path)
    feedback_path = output_dir / "candidate_feedback.json"
    feedback = _load_json(feedback_path) if feedback_path.exists() else None
    feedback_by_id = _feedback_by_id(feedback)
    output_dir.mkdir(parents=True, exist_ok=True)
    filter_suffix = _filter_suffix(args.candidate_type, args.risk_level) if (args.candidate_type or args.risk_level) else None

    common = {
        "top_n": args.top_n,
        "crop_padding": args.crop_padding,
        "candidate_type": args.candidate_type,
        "risk_level": args.risk_level,
        "feedback_by_id": feedback_by_id,
    }
    output_paths = {}
    rendered_total = 0
    skipped_total = 0

    if args.candidate_type or args.risk_level:
        suffix = _filter_suffix(args.candidate_type, args.risk_level)
        overlay = render_candidate_overlay(
            str(base_image),
            plan,
            geometry,
            str(output_dir / f"candidate_overlay_{suffix}.png"),
            common,
        )
        sheet = render_candidate_contact_sheet(
            str(base_image),
            plan,
            geometry,
            str(output_dir / f"candidate_contact_sheet_{suffix}.png"),
            common,
        )
        output_paths["filtered_overlay"] = overlay["output_path"]
        output_paths["filtered_contact_sheet"] = sheet["output_path"]
        rendered_total += overlay["rendered_candidates"] + sheet["rendered_candidates"]
        skipped_total += overlay["skipped_candidates"] + sheet["skipped_candidates"]
    else:
        for name, options in (
            ("all", {}),
            ("low", {"risk_level": "low"}),
            ("review_only", {"risk_level": "review_only"}),
        ):
            result = render_candidate_overlay(
                str(base_image),
                plan,
                geometry,
                str(output_dir / f"candidate_overlay_{name}.png"),
                {**common, **options},
            )
            output_paths[f"overlay_{name}"] = result["output_path"]
            rendered_total += result["rendered_candidates"]
            skipped_total += result["skipped_candidates"]

        sheets = (
            ("top_50", {}),
            ("low_alpha", {"candidate_type": "low_alpha_large_soft_shape"}),
            ("ellipse_cluster", {"candidate_type": "ellipse_cluster_member"}),
        )
        for name, options in sheets:
            result = render_candidate_contact_sheet(
                str(base_image),
                plan,
                geometry,
                str(output_dir / f"candidate_contact_sheet_{name}.png"),
                {**common, **options},
            )
            output_paths[f"contact_sheet_{name}"] = result["output_path"]
            rendered_total += result["rendered_candidates"]
            skipped_total += result["skipped_candidates"]

    if not args.no_crops:
        crop_result = export_candidate_crops(
            str(base_image),
            plan,
            geometry,
            str(output_dir / "crops"),
            common,
        )
        output_paths["crops"] = crop_result["output_dir"]
        output_paths["crop_paths_sample"] = crop_result["crop_paths"][:10]
        rendered_total += crop_result["rendered_candidates"]
        skipped_total += crop_result["skipped_candidates"]

    csv_name = f"candidate_review_table_{filter_suffix}.csv" if filter_suffix else "candidate_review_table.csv"
    summary_name = f"review_summary_{filter_suffix}.txt" if filter_suffix else "review_summary.txt"
    index_name = f"candidate_review_index_{filter_suffix}.json" if filter_suffix else "candidate_review_index.json"
    output_paths["csv"] = write_candidate_review_csv(plan, output_dir / csv_name)
    output_paths["summary"] = write_review_summary(plan, output_dir / summary_name)
    output_paths["base_image"] = str(base_image)
    index = write_candidate_review_index(
        plan,
        output_dir / index_name,
        {
            **output_paths,
            "rendered_candidates": rendered_total,
            "skipped_candidates": skipped_total,
        },
        warnings=[],
        feedback=feedback,
    )
    return {
        "output_dir": str(output_dir),
        "total_candidates": index["total_candidates"],
        "rendered_candidates": rendered_total,
        "skipped_candidates": skipped_total,
        "index": index,
    }


def _find_base_image(case_dir):
    candidates = [
        case_dir / "source_renderer" / "export_variants" / "cropped_transparent_padding_8.png",
        case_dir / "source_renderer" / "paintstudio_source_renderer_preview.png",
        case_dir / "optimized_preview.png",
        case_dir / "flo_preview.png",
        case_dir / "source_full.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No base image found for case: {case_dir}")


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def _feedback_by_id(feedback):
    if not isinstance(feedback, dict):
        return {}
    return {item.get("change_id"): item for item in feedback.get("items", []) if item.get("change_id")}


def _filter_suffix(candidate_type, risk_level):
    parts = []
    if candidate_type:
        parts.append(candidate_type)
    if risk_level:
        parts.append(risk_level)
    return "_".join(parts) if parts else "all"


if __name__ == "__main__":
    raise SystemExit(main())
