import copy
from collections import Counter

import numpy as np

from engine.optimizer.change_plan import make_shape_uid
from engine.vision.semantic_regions.region_schema import SENSITIVE_LABELS
from .shape_visibility_analyzer import iter_visible_shape_masks


def attribute_layers_to_semantic_regions(geometry,semantic_region_result,visibility_result,options=None):
    options=options or {}; original=copy.deepcopy(geometry); scale=float(options.get("visibility_resolution_scale",1.0))
    masks=semantic_region_result["_masks"]; height,width=next(iter(masks.values())).shape
    scaled_masks={label:_resize_mask(mask,scale) for label,mask in masks.items()}; visibility_by={item["shape_index"]:item for item in visibility_result["shapes"]}
    threshold=float(options.get("attribution_overlap_threshold",.12)); margin=float(options.get("ambiguity_margin",.08)); layers=[]
    for index,mask,visible in iter_visible_shape_masks(geometry,width,height,scale):
        shape=geometry["shapes"][index]; visibility=visibility_by[index]; entry=_attribute(shape,index,visible,visibility,scaled_masks,threshold,margin); layers.append(entry)
    layers.sort(key=lambda item:item["shape_index"]); summaries=_summaries(layers,semantic_region_result,options)
    counts=Counter(item["attribution_status"] for item in layers)
    warnings=list(visibility_result.get("warnings",[]))
    return {"layer_region_attribution_version":"0.7.0","status":"completed_with_warnings" if warnings else "completed",
        "geometry_path":options.get("geometry_path"),"semantic_regions_path":options.get("semantic_regions_path"),"shape_count":len(layers),
        "attributed_shape_count":sum(item["attribution_status"] in {"assigned","ambiguous"} for item in layers),
        "fully_occluded_shape_count":counts["fully_occluded"],"ambiguous_shape_count":counts["ambiguous"],
        "unknown_shape_count":counts["unknown"]+counts["unsupported"],"sensitive_shape_count":sum(item["sensitive_region"] for item in layers),
        "attribution_basis":"occlusion_aware_alpha_visibility","layers":layers,"region_summaries":summaries,
        "safety":{"original_geometry_modified":geometry!=original,"official_optimization_output_written":False,"analysis_only":True},"warnings":warnings}


def _attribute(shape,index,visible,visibility,masks,threshold,margin):
    base={"shape_index":index,"shape_uid":make_shape_uid(shape,index),"shape_type":shape.get("type"),
        "total_alpha_area":visibility["total_alpha_area"],"estimated_visible_alpha_area":visibility["estimated_visible_alpha_area"],
        "estimated_occlusion_ratio":visibility["estimated_occlusion_ratio"],"attribution_basis":"occlusion_aware_alpha_visibility","warnings":[]}
    if visible is None: return {**base,"primary_region":"unknown","primary_region_overlap_ratio":0.0,"secondary_regions":[],"all_region_overlaps":{},"outline_overlap_ratio":0.0,"sensitive_region":False,"sensitive_labels":[],"attribution_confidence":0.0,"attribution_status":"unsupported"}
    area=float(visible.sum())
    if area<=1e-5: return {**base,"primary_region":"unknown","primary_region_overlap_ratio":0.0,"secondary_regions":[],"all_region_overlaps":{},"outline_overlap_ratio":0.0,"sensitive_region":False,"sensitive_labels":[],"attribution_confidence":1.0,"attribution_status":"fully_occluded"}
    overlaps={label:float((visible*mask).sum()/area) for label,mask in masks.items() if label!="outline_edge"}
    ranked=sorted(overlaps.items(),key=lambda item:(-item[1],item[0])); primary,ratio=ranked[0]
    if ratio<threshold: primary="foreground_unknown" if overlaps.get("foreground_unknown",0)>0 else "unknown"; status="unknown"
    else: status="ambiguous" if len(ranked)>1 and ratio-ranked[1][1]<margin else "assigned"
    secondary=[{"label":label,"overlap_ratio":round(value,6)} for label,value in ranked[1:] if value>=threshold]
    outline=float((visible*masks.get("outline_edge",False)).sum()/area); sensitive=[label for label in SENSITIVE_LABELS if (outline if label=="outline_edge" else overlaps.get(label,0))>=threshold]
    return {**base,"primary_region":primary,"primary_region_overlap_ratio":round(ratio,6),"secondary_regions":secondary,
        "all_region_overlaps":{k:round(v,6) for k,v in overlaps.items()},"outline_overlap_ratio":round(outline,6),
        "sensitive_region":bool(sensitive),"sensitive_labels":sorted(sensitive),"attribution_confidence":round(max(0,min(1,ratio-(ranked[1][1] if len(ranked)>1 else 0)+.25)),6),"attribution_status":status}


def _summaries(layers,regions,options):
    records={item["label"]:item for item in regions["regions"]}; summaries={}; plan=options.get("plan") or {}; visible=options.get("visible_contribution_report") or {}
    candidate_by={change.get("shape_index"):(change.get("metadata") or {}).get("candidate_type") for change in plan.get("changes",[])}
    action_by={item.get("shape_index"):item.get("recommended_action") for item in visible.get("results",[])}
    for label,record in records.items():
        related=[item for item in layers if item["primary_region"]==label or label in item.get("all_region_overlaps",{}) and item["all_region_overlaps"][label]>.05]
        primary=[item for item in layers if item["primary_region"]==label]; shape_types=Counter(str(item["shape_type"]) for item in primary)
        actions=Counter(action_by.get(item["shape_index"]) for item in related if action_by.get(item["shape_index"])); candidates=Counter(candidate_by.get(item["shape_index"]) for item in related if candidate_by.get(item["shape_index"]))
        summaries[label]={"region_label":label,"region_confidence":record["confidence"],"foreground_pixel_area":record["pixel_area"],
            "attributed_shape_count":len(related),"primary_attributed_shape_count":len(primary),"cross_region_shape_count":sum(bool(item["secondary_regions"]) for item in related),
            "estimated_visible_layer_area":round(sum(item["estimated_visible_alpha_area"] for item in related),3),
            "estimated_occluded_layer_area":round(sum(item["total_alpha_area"]-item["estimated_visible_alpha_area"] for item in related),3),
            "shape_type_distribution":dict(shape_types),"alpha_distribution":{"mean_visible_alpha_area":round(sum(item["estimated_visible_alpha_area"] for item in related)/max(1,len(related)),3)},
            "candidate_type_distribution":dict(candidates),"safe_delete_count":actions["safe_delete_pool"],"replacement_count":actions["replacement_candidate"],"protect_count":actions["protect_candidate"],
            "layer_budget_ratio":round(len(primary)/max(1,len(layers)),6),"complexity_indicators":{"ambiguous_count":sum(item["attribution_status"]=="ambiguous" for item in related)},"warnings":[]}
    return summaries


def _resize_mask(mask,scale):
    if scale==1: return np.asarray(mask,dtype=np.float32)
    from PIL import Image
    h,w=mask.shape; return np.asarray(Image.fromarray(mask.astype("uint8")*255).resize((max(1,int(round(w*scale))),max(1,int(round(h*scale)))),Image.Resampling.NEAREST),dtype=np.float32)/255
