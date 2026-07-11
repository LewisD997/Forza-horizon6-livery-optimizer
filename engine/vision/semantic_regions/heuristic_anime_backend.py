import json
from pathlib import Path

import numpy as np
from PIL import Image

from .region_postprocess import build_label_map, fill_small_holes, filter_components, region_records, resolve_exclusive_masks, validate_partition
from .region_schema import EXCLUSIVE_LABELS, SEMANTIC_REGION_VERSION
from .component_topology import build_component_topology, neighbors, public_topology
from .stripe_diagnostics import analyze_semantic_stripes


BACKEND = "heuristic_anime_v1"


def generate_heuristic_anime_proposal(image_path, options=None):
    options = options or {}; path = Path(image_path)
    rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8); rgb = rgba[:, :, :3]; alpha = rgba[:, :, 3]
    h, w = alpha.shape; warnings = []; diagnostics = {}
    threshold = int(options.get("foreground_alpha_threshold", 0))
    domain, extraction = _foreground(rgb, alpha, threshold)
    before_count = int(domain.sum())
    # Source alpha is the immutable semantic domain. Component filtering may
    # affect individual proposals, but never the foreground partition itself.
    foreground = np.array(domain, copy=True)
    extraction.update({"foreground_before_postprocess": before_count, "foreground_after_postprocess": int(foreground.sum()),
        "pixels_added_by_postprocess": int((foreground & ~domain).sum()), "pixels_removed_by_postprocess": int((domain & ~foreground).sum()),
        "transparent_pixels_added": int((foreground & (alpha <= threshold)).sum()),
        "foreground_domain_match_ratio": round(float((foreground == domain).sum()/domain.size), 8)})
    clusters, centers, cluster_diag = _quantize(rgb, foreground, int(options.get("color_clusters", 12)))
    topology=build_component_topology(rgb,clusters,foreground,int(options.get("component_gap",2)))
    diagnostics.update({"foreground_source": extraction["mode"], "foreground_extraction": extraction,
        "color_clustering": cluster_diag, "color_cluster_centers_rgb": centers, "color_cluster_count": len(centers)})
    masks, confidences, eye_diag, face_diag = _semantic_masks(rgb, foreground, clusters, centers, topology, options)
    _apply_hints(masks, confidences, options.get("region_hints"), w, h, warnings)
    for label in masks: masks[label] &= domain
    exclusive = resolve_exclusive_masks(masks, foreground)
    outline = _outline_mask(foreground, rgb) & domain
    label_map = build_label_map(exclusive)
    stripe_diag=analyze_semantic_stripes(label_map,domain)
    confidence_map = np.zeros((h, w), dtype=np.float32)
    for label, mask in exclusive.items(): confidence_map[mask] = confidences.get(label, 1.0 if label == "background" else 0.3)
    fg_count = int(foreground.sum()); unknown = int(exclusive["foreground_unknown"].sum())
    unknown_ratio = unknown / max(1, fg_count)
    if unknown_ratio > float(options.get("unknown_warning_threshold", 0.65)): warnings.append("Foreground unknown ratio is high; semantic proposal is intentionally conservative.")
    records = region_records(exclusive, confidences, fg_count, BACKEND)
    semantic_leak = sum(int((mask & ~domain).sum()) for label,mask in exclusive.items() if label != "background")
    strict = extraction["meaningful_alpha_detected"]
    source_transparent = extraction["source_transparent_pixel_count"]
    background_recall = float((exclusive["background"] & (alpha <= threshold)).sum()/max(1,source_transparent)) if strict else None
    guardrails={"transparent_semantic_leak_count":semantic_leak,"transparent_semantic_leak_ratio":round(semantic_leak/max(1,source_transparent),8),
        "semantic_pixels_outside_foreground_count":semantic_leak,"exclusive_partition_valid":validate_partition(exclusive,foreground)}
    diagnostics.update({"semantic_guardrails":guardrails,"eye_detection":eye_diag,"face_core":face_diag,
        "component_topology":public_topology(topology),"semantic_stripes":stripe_diag})
    coverage = {"foreground_pixel_count": fg_count, "classified_foreground_pixel_count": fg_count - unknown,
        "foreground_unknown_pixel_count": unknown, "foreground_unknown_ratio": round(unknown_ratio, 6),
        "background_pixel_count": int((~foreground).sum()), "exclusive_partition_valid": validate_partition(exclusive, foreground),
        "source_transparent_pixel_count":source_transparent,"source_nontransparent_pixel_count":extraction["source_nontransparent_pixel_count"],
        "transparent_semantic_leak_count":semantic_leak,"transparent_semantic_leak_ratio":guardrails["transparent_semantic_leak_ratio"],
        "transparent_background_recall":round(background_recall,8) if background_recall is not None else None,
        "foreground_domain_match_ratio":extraction["foreground_domain_match_ratio"],"semantic_pixels_outside_foreground_count":semantic_leak,
        "clustered_background_pixel_count":cluster_diag["clustered_background_pixel_count"],"strict_source_alpha":strict}
    status = "completed_with_warnings" if warnings else "completed"
    return {"semantic_region_version": SEMANTIC_REGION_VERSION, "status": status, "backend": BACKEND,
        "image_path": str(path), "image_size": {"width": w, "height": h}, "labels": list(EXCLUSIVE_LABELS),
        "regions": records, "coverage": coverage,
        "confidence_summary": {label: round(float(confidences.get(label, 0.0)), 4) for label in EXCLUSIVE_LABELS},
        "diagnostics": diagnostics, "warnings": warnings,
        "_masks": {**exclusive, "outline_edge": outline}, "_label_map": label_map, "_confidence_map": confidence_map,
        "_semantic_domain": domain, "_source_transparent": alpha <= threshold,"_face_core":face_diag.pop("_mask",np.zeros_like(domain))}


def _foreground(rgb, alpha, threshold):
    transparent = int((alpha <= threshold).sum()); nontransparent = int((alpha > threshold).sum())
    meaningful = transparent > 0 and nontransparent > 0
    base={"alpha_min":int(alpha.min()),"alpha_max":int(alpha.max()),"source_transparent_pixel_count":transparent,
        "source_nontransparent_pixel_count":nontransparent,"alpha_background_threshold":threshold,"meaningful_alpha_detected":meaningful}
    if meaningful: return alpha > threshold, {**base,"mode":"source_alpha_strict"}
    border = np.concatenate((rgb[0], rgb[-1], rgb[:,0], rgb[:,-1]), axis=0).astype(np.float32)
    bg = np.median(border, axis=0); distance = np.sqrt(((rgb.astype(np.float32)-bg) ** 2).sum(axis=2))
    threshold_value = max(18.0, float(np.percentile(np.sqrt(((border-bg)**2).sum(axis=1)), 90)) + 10.0)
    fallback=distance > threshold_value
    return fallback, {**base,"mode":"border_color_separation","fallback_distance_threshold":threshold_value}


def _quantize(rgb, foreground, count):
    pixels=rgb[foreground]; labels=np.full(foreground.shape,-1,dtype=np.int16)
    if len(pixels)==0: return labels,[],{"clustered_pixel_count":0,"excluded_background_pixel_count":int(foreground.size),"clustered_background_pixel_count":0,"cluster_pixel_total":0}
    strip=Image.fromarray(pixels.reshape(1,-1,3),"RGB"); quantized=strip.quantize(colors=max(2,min(32,count)),method=Image.Quantize.MEDIANCUT)
    pixel_labels=np.asarray(quantized,dtype=np.int16).reshape(-1); labels[foreground]=pixel_labels; palette=quantized.getpalette(); centers=[]
    for index in sorted(int(value) for value in np.unique(pixel_labels)):
        centers.append({"cluster_id":index,"rgb":palette[index*3:index*3+3],"pixel_count":int((pixel_labels==index).sum())})
    total=sum(item["pixel_count"] for item in centers)
    return labels,centers,{"clustered_pixel_count":int(len(pixels)),"excluded_background_pixel_count":int((~foreground).sum()),"clustered_background_pixel_count":0,"cluster_pixel_total":total}


def _semantic_masks(rgb, foreground, clusters, centers, topology, options):
    h,w = foreground.shape; yy,xx = np.indices((h,w)); ys,xs = np.where(foreground)
    if len(xs) == 0: return {}, {"background": 1.0, "foreground_unknown": 1.0}, {"candidate_count":0,"accepted_count":0,"rejected_candidates":[],"eye_mask_area":0,"eye_to_face_area_ratio":None,"eye_bbox":None,"paired_eye_evidence":False}, {"exists":False,"confidence":0.0,"bbox":None,"component_ids":[],"_mask":np.zeros_like(foreground)}
    x0,x1,y0,y1 = xs.min(),xs.max()+1,ys.min(),ys.max()+1; fw=max(1,x1-x0); fh=max(1,y1-y0)
    r,g,b = [rgb[:,:,i].astype(np.float32) for i in range(3)]
    maximum=np.maximum.reduce([r,g,b]); minimum=np.minimum.reduce([r,g,b]); saturation=(maximum-minimum)/(maximum+1)
    skin_color = (r > 105) & (r >= g*.92) & (r >= b*.9) & ((r-b)>5) & (saturation < .48)
    skin_candidates = filter_components(foreground & skin_color, max(8, int(foreground.sum()*.001)), False)
    face,face_conf,face_ids=_select_face_core(topology,skin_candidates,(x0,y0,fw,fh),foreground)
    body_skin=skin_candidates&~face
    expanded_face=_dilate(face,max(2,int(min(fw,fh)*.06)))&foreground if face.any() else np.zeros_like(face)
    hair,clothing=_propagate_hair_clothing(topology,foreground,skin_candidates,face,expanded_face,(x0,y0,fw,fh))
    # Compact high-contrast components in the upper half of a confident face.
    gray = rgb.mean(axis=2); local_dark = gray < np.percentile(gray[face], 35) if face.any() else np.zeros_like(face)
    face_bbox=_mask_bbox(face); eye_zone=np.zeros_like(face)
    if face_bbox:
        fy0=face_bbox["y"]+face_bbox["height"]*.18; fy1=face_bbox["y"]+face_bbox["height"]*.62
        eye_zone=face&(yy>=fy0)&(yy<=fy1)
    eyes = np.zeros_like(face); rejected=[]; candidate_count=0; accepted=[]
    if face_conf >= .42:
        for component in __import__("engine.vision.semantic_regions.region_postprocess", fromlist=["connected_components"]).connected_components(eye_zone & local_dark):
            candidate_count+=1; cy,cx=zip(*component); bw=max(cx)-min(cx)+1; bh=max(cy)-min(cy)+1; area=len(component); area_ratio=area/max(1,int(face.sum())); aspect=bw/max(1,bh)
            reasons=[]
            if area<int(options.get("eye_minimum_area",2)): reasons.append("area_below_minimum")
            if area>int(options.get("eye_maximum_area",max(12,int(face.sum()*.025)))) or area_ratio>float(options.get("eye_maximum_face_area_ratio",.025)): reasons.append("area_too_large")
            if not .35<=aspect<=5.0: reasons.append("aspect_ratio")
            if bw>fw*.18 or bh>fh*.10: reasons.append("bbox_too_large")
            values=gray[np.array(cy),np.array(cx)]; contrast=float(gray[face].mean()-values.mean()) if face.any() else 0
            if contrast<float(options.get("eye_minimum_contrast",18)): reasons.append("low_contrast")
            if reasons: rejected.append({"bbox":{"x":min(cx),"y":min(cy),"width":bw,"height":bh},"area":area,"reasons":reasons}); continue
            accepted.append({"cy":np.array(cy),"cx":np.array(cx),"center":(float(np.mean(cx)),float(np.mean(cy))),"contrast":contrast,"area":area})
    accepted.sort(key=lambda item:(-item["contrast"],-item["area"],item["center"][0]))
    selected=[]; maximum_total=max(1,int(face.sum()*float(options.get("eye_maximum_total_face_area_ratio",.025))))
    for item in accepted:
        if len(selected)>=2 or int(eyes.sum())+item["area"]>maximum_total:
            rejected.append({"bbox":_component_bbox(item["cy"],item["cx"]),"area":item["area"],"reasons":["aggregate_eye_guardrail"]}); continue
        eyes[item["cy"],item["cx"]]=True; selected.append(item)
    mouth_zone=np.zeros_like(face)
    if face_bbox:
        mouth_zone=face&(yy>face_bbox["y"]+face_bbox["height"]*.55)&(yy<face_bbox["y"]+face_bbox["height"]*.88)
    reddish = (r > g*1.08) & (r > b*1.03) & (saturation > .12)
    mouth = filter_components(mouth_zone & reddish, 2, False)
    if mouth.sum() > max(20, face.sum()*.05): mouth[:] = False
    clothing &= ~(face|body_skin|hair|eyes|mouth)
    eye_area=int(eyes.sum()); eye_bbox=_mask_bbox(eyes); paired=bool(len(selected)>=2 and abs(selected[0]["center"][1]-selected[1]["center"][1])<fh*.08)
    eye_diag={"candidate_count":candidate_count,"accepted_count":len(selected),"rejected_candidates":rejected[:50],"eye_mask_area":eye_area,
        "eye_to_face_area_ratio":round(eye_area/max(1,int(face.sum())),8) if face.any() else None,"eye_bbox":eye_bbox,"paired_eye_evidence":paired}
    return {"hair": hair, "face_skin": face, "eyes": eyes, "mouth": mouth, "body_skin": body_skin, "clothing": clothing}, {
        "background": .98, "foreground_unknown": .3, "face_skin": face_conf,
        "body_skin": .5 if body_skin.any() else .2, "hair": .58 if hair.any() else .25,
        "eyes": .62 if eyes.any() else .15, "mouth": .52 if mouth.any() else .12,
        "clothing": .48 if clothing.any() else .2,
    }, eye_diag,{"exists":bool(face.any()),"confidence":round(float(face_conf),4),"bbox":face_bbox,"component_ids":face_ids,"pixel_area":int(face.sum()),"_mask":face.copy()}


def _select_face_core(topology,skin_candidates,fg_box,foreground):
    x0,y0,fw,fh=fg_box; candidates=[]
    for node in topology["nodes"]:
        overlap=int((node["_mask"]&skin_candidates).sum())
        if overlap<max(12,node["pixel_count"]*.55): continue
        box=node["bbox"]; aspect=box["width"]/max(1,box["height"]); area_ratio=overlap/max(1,int(foreground.sum()))
        compact=0.4<=aspect<=2.2 and .002<=area_ratio<=.22
        cx=node["centroid"]["x"]; cy=node["centroid"]["y"]
        central=max(0,1-abs(cx-(x0+fw*.5))/max(1,fw*.5)); head_prior=max(0,1-(cy-y0)/max(1,fh))
        score=.42*central+.28*head_prior+.3*(1 if compact else 0)
        if compact: candidates.append((score,node))
    if not candidates: return np.zeros_like(foreground),.2,[]
    score,seed=max(candidates,key=lambda item:(item[0],item[1]["pixel_count"])); mask=seed["_mask"]&skin_candidates; ids=[seed["component_id"]]
    for node in neighbors(topology,seed["component_id"]):
        if int((node["_mask"]&skin_candidates).sum())>=node["pixel_count"]*.7 and node["pixel_count"]<seed["pixel_count"]*.35:
            mask|=node["_mask"]&skin_candidates; ids.append(node["component_id"])
    confidence=min(.78,.38+score*.35)
    if confidence<.48: return np.zeros_like(foreground),confidence,[]
    return mask,confidence,ids


def _propagate_hair_clothing(topology,foreground,skin,face,face_near,fg_box):
    x0,y0,fw,fh=fg_box; non_skin=foreground&~skin; hair_ids=set(); clothing_ids=set(); by_id={node["component_id"]:node for node in topology["nodes"]}
    for node in topology["nodes"]:
        usable=node["_mask"]&non_skin
        if usable.sum()<max(8,node["pixel_count"]*.5): continue
        near_face=int((node["_mask"]&face_near).sum())>0; cy=node["centroid"]["y"]; area=node["pixel_count"]
        head_soft=max(0,1-(cy-y0)/max(1,fh*.58)); torso_soft=max(0,min(1,(cy-(y0+fh*.28))/max(1,fh*.55)))
        if near_face or head_soft>.72: hair_ids.add(node["component_id"])
        elif torso_soft>.45 and area>foreground.sum()*.003: clothing_ids.add(node["component_id"])
    changed=True
    while changed:
        changed=False
        for node in topology["nodes"]:
            cid=node["component_id"]
            if cid in hair_ids or cid in clothing_ids: continue
            linked=neighbors(topology,cid); hair_links=[other for other in linked if other["component_id"] in hair_ids]; clothing_links=[other for other in linked if other["component_id"] in clothing_ids]
            if hair_links and not clothing_links and min(_color_distance(node,other) for other in hair_links)<42: hair_ids.add(cid); changed=True
            elif clothing_links and not hair_links and min(_color_distance(node,other) for other in clothing_links)<42: clothing_ids.add(cid); changed=True
    hair=np.zeros_like(foreground); clothing=np.zeros_like(foreground)
    for cid in hair_ids: hair|=by_id[cid]["_mask"]&non_skin
    for cid in clothing_ids-hair_ids: clothing|=by_id[cid]["_mask"]&non_skin
    return hair,clothing


def _color_distance(a,b): return sum((x-y)**2 for x,y in zip(a["mean_color"],b["mean_color"]))**.5


def _mask_bbox(mask):
    ys,xs=np.where(mask)
    if not len(xs): return None
    return {"x":int(xs.min()),"y":int(ys.min()),"width":int(xs.max()-xs.min()+1),"height":int(ys.max()-ys.min()+1)}


def _component_bbox(ys,xs):
    return {"x":int(xs.min()),"y":int(ys.min()),"width":int(xs.max()-xs.min()+1),"height":int(ys.max()-ys.min()+1)}


def _dilate(mask, radius):
    out=np.array(mask,copy=True); h,w=out.shape
    for _ in range(min(radius,12)):
        padded=np.pad(out,1); out = padded[1:h+1,1:w+1]|padded[:-2,1:w+1]|padded[2:,1:w+1]|padded[1:h+1,:-2]|padded[1:h+1,2:]
    return out


def _outline_mask(foreground, rgb):
    eroded = foreground.copy(); h,w=foreground.shape; p=np.pad(foreground,1,constant_values=False)
    eroded &= p[:-2,1:w+1]&p[2:,1:w+1]&p[1:h+1,:-2]&p[1:h+1,2:]
    external = foreground & ~eroded
    gray=rgb.astype(np.float32).mean(axis=2); gx=np.zeros_like(gray); gy=np.zeros_like(gray); gx[:,1:]=abs(gray[:,1:]-gray[:,:-1]); gy[1:]=abs(gray[1:]-gray[:-1])
    return external | (foreground & ((gx+gy)>80))


def _apply_hints(masks, confidences, path, width, height, warnings):
    if not path: return
    try: hints=json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc: warnings.append(f"Region hints could not be read: {exc}"); return
    for box in hints.get("boxes", []):
        label=box.get("label")
        if label not in masks: continue
        x=max(0,int(box.get("x",0))); y=max(0,int(box.get("y",0))); x1=min(width,x+max(0,int(box.get("width",0)))); y1=min(height,y+max(0,int(box.get("height",0))))
        masks[label][y:y1,x:x1]=True; confidences[label]=min(1.0,confidences.get(label,.3)+.15)
    for point in hints.get("positive_points", []):
        label=point.get("label"); x=int(point.get("x",-1)); y=int(point.get("y",-1))
        if label in masks and 0<=x<width and 0<=y<height: masks[label][y,x]=True; confidences[label]=min(1.0,confidences.get(label,.3)+.08)
    for point in hints.get("negative_points", []):
        label=point.get("label"); x=int(point.get("x",-1)); y=int(point.get("y",-1))
        if label in masks and 0<=x<width and 0<=y<height:
            masks[label][y,x]=False; confidences[label]=max(0.0,confidences.get(label,.3)-.05)
