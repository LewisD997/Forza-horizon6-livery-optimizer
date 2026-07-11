import copy
import csv
import json
from pathlib import Path

from engine.vision.semantic_regions.region_schema import REGION_IDS, VALID_LABELS


def write_semantic_regions_json(result,path,overwrite=False): return _write_json(_public(result),path,overwrite)
def write_layer_region_attribution_json(result,path,overwrite=False): return _write_json(result,path,overwrite)
def write_region_layer_summary(summary,path,overwrite=False): return _write_json(summary,path,overwrite)


def write_layer_region_attribution_csv(result,path,overwrite=False):
    output=_guard(path,overwrite); fields=["shape_index","shape_uid","shape_type","primary_region","primary_region_overlap_ratio","estimated_visible_alpha_area","estimated_occlusion_ratio","attribution_status","sensitive_region","sensitive_labels"]
    with output.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for item in result["layers"]:
            row={key:item.get(key) for key in fields}; row["sensitive_labels"]="|".join(item.get("sensitive_labels",[])); writer.writerow(row)
    return str(output)


def validate_semantic_region_result(result):
    required={"semantic_region_version","status","backend","image_path","image_size","labels","regions","coverage","confidence_summary","diagnostics","warnings"}
    if required-set(result): raise ValueError(f"Semantic result missing: {sorted(required-set(result))}")
    for record in result["regions"]:
        if record["label"] not in VALID_LABELS or not 0<=record["confidence"]<=1: raise ValueError("Invalid semantic region record.")
    coverage=result["coverage"]
    required_coverage={"source_transparent_pixel_count","source_nontransparent_pixel_count","transparent_semantic_leak_count",
        "transparent_semantic_leak_ratio","transparent_background_recall","foreground_domain_match_ratio",
        "semantic_pixels_outside_foreground_count","clustered_background_pixel_count"}
    if required_coverage-set(coverage): raise ValueError(f"Coverage guardrails missing: {sorted(required_coverage-set(coverage))}")
    if coverage.get("exclusive_partition_valid") is not True: raise ValueError("Exclusive semantic partition is invalid.")
    if coverage.get("strict_source_alpha"):
        if coverage["transparent_semantic_leak_count"]!=0 or coverage["semantic_pixels_outside_foreground_count"]!=0: raise ValueError("Strict alpha semantic leak detected.")
        if coverage["clustered_background_pixel_count"]!=0: raise ValueError("Background pixels entered color clustering.")
        if coverage["transparent_background_recall"]!=1.0 or coverage["foreground_domain_match_ratio"]!=1.0: raise ValueError("Strict alpha domain does not match source alpha.")
    return True


def validate_layer_region_attribution(result):
    required={"layer_region_attribution_version","status","shape_count","layers","region_summaries","safety"}
    if required-set(result): raise ValueError(f"Attribution missing: {sorted(required-set(result))}")
    if len(result["layers"])!=result["shape_count"]: raise ValueError("One attribution is required per shape.")
    for item in result["layers"]:
        if any(not 0<=value<=1 for value in item.get("all_region_overlaps",{}).values()): raise ValueError("Invalid overlap ratio.")
    safety=result["safety"]
    if safety.get("analysis_only") is not True or safety.get("original_geometry_modified") is not False or safety.get("official_optimization_output_written") is not False: raise ValueError("Attribution safety flags are invalid.")
    return True


def _public(result): return {key:copy.deepcopy(value) for key,value in result.items() if not key.startswith("_")}
def _write_json(data,path,overwrite):
    output=_guard(path,overwrite); output.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8"); return str(output)
def _guard(path,overwrite):
    output=Path(path)
    if output.exists() and not overwrite: raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True); return output
