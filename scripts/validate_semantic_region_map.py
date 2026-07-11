import argparse,json,sys
import numpy as np
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.optimizer.change_plan import make_shape_uid
from engine.output.semantic_region_writer import validate_layer_region_attribution,validate_semantic_region_result
from engine.vision.semantic_regions.region_schema import PALETTE,REGION_IDS,SENSITIVE_LABELS


def validate_outputs(regions,attribution,geometry):
    validate_semantic_region_result(regions); validate_layer_region_attribution(attribution)
    width,height=regions["image_size"]["width"],regions["image_size"]["height"]
    for record in regions["regions"]:
        if record.get("mask_path") and Image.open(record["mask_path"]).size!=(width,height): raise ValueError("Region mask size mismatch.")
    map_value=(regions.get("outputs") or {}).get("region_map")
    map_path=Path(map_value) if map_value else None
    if map_path and map_path.exists():
        region_map=Image.open(map_path)
        if region_map.size!=(width,height): raise ValueError("Semantic map size mismatch.")
        if region_map.mode!="P": raise ValueError("Semantic map must store exact numeric label IDs in palette mode.")
        if set(np.unique(np.asarray(region_map)))-set(REGION_IDS.values()): raise ValueError("Semantic map contains invalid label IDs.")
        coverage=regions["coverage"]
        if coverage.get("strict_source_alpha"):
            source_alpha=np.asarray(Image.open(regions["image_path"]).convert("RGBA"))[:,:,3]
            threshold=int((regions.get("diagnostics",{}).get("foreground_extraction") or {}).get("alpha_background_threshold",0))
            transparent=source_alpha<=threshold; label_values=np.asarray(region_map)
            if np.any(label_values[transparent]!=REGION_IDS["background"]): raise ValueError("Semantic foreground label exists in a source-transparent pixel.")
            if int(transparent.sum())!=coverage["source_transparent_pixel_count"]: raise ValueError("Source transparent count mismatch.")
    if attribution["shape_count"]!=len(geometry.get("shapes",[])): raise ValueError("Shape count mismatch.")
    diagnostics=regions.get("diagnostics") or {}; topology=diagnostics.get("component_topology") or {}; stripes=diagnostics.get("semantic_stripes") or {}; face=diagnostics.get("face_core") or {}
    if topology.get("component_count")!=len(topology.get("nodes",[])): raise ValueError("Component topology is invalid.")
    if stripes.get("hard_horizontal_semantic_thresholds") not in ([],None): raise ValueError("Hard horizontal semantic thresholds are forbidden.")
    if face.get("exists") and (not face.get("bbox") or face.get("confidence",0)<.45): raise ValueError("Face core lacks sufficient confidence or bbox.")
    output_dir=Path(regions["outputs"]["region_map"]).parent if (regions.get("outputs") or {}).get("region_map") else None
    if output_dir:
        stripe_path=output_dir/"semantic_stripe_diagnostics.json"; alignment_path=output_dir/"semantic_attribution_alignment_audit.json"; background_path=output_dir/"background_attribution_review.json"
        for path in (stripe_path,alignment_path,background_path):
            if not path.exists(): raise ValueError(f"Required semantic audit output missing: {path.name}")
        alignment=_load(alignment_path); background_review=_load(background_path)
        if alignment.get("alignment_confidence") not in {"high","medium","low"}: raise ValueError("Invalid alignment audit confidence.")
        if background_review.get("base_shape_excluded") is not True: raise ValueError("Background review must exclude base shape.")
    if len(attribution["layers"])!=len(geometry["shapes"]): raise ValueError("Missing attribution records.")
    for index,item in enumerate(attribution["layers"]):
        if item["shape_index"]!=index or item["shape_uid"]!=make_shape_uid(geometry["shapes"][index],index): raise ValueError("Shape identity mismatch.")
        if any(label not in SENSITIVE_LABELS|{"face_core"} for label in item["sensitive_labels"]): raise ValueError("Invalid sensitive label.")
        if item.get("sensitive_region") and not item.get("sensitive_triggers"): raise ValueError("Sensitive attribution lacks trigger metadata.")
        if item["attribution_status"]=="fully_occluded" and item["estimated_visible_alpha_area"]>1e-4: raise ValueError("Fully occluded shape has visible area.")
        if sum(item.get("all_region_overlaps",{}).values())>1.001: raise ValueError("Region overlaps are inconsistent.")
    return True


def main():
    p=argparse.ArgumentParser(); p.add_argument("--regions",required=True); p.add_argument("--attribution",required=True); p.add_argument("--geometry",required=True); args=p.parse_args()
    try: validate_outputs(_load(args.regions),_load(args.attribution),_load(args.geometry))
    except Exception as exc: print(f"Semantic region validation failed: {exc}",file=sys.stderr); return 1
    print("Semantic region map and layer attribution validation passed."); return 0
def _load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
if __name__=="__main__": raise SystemExit(main())
