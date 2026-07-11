import json
from pathlib import Path

import numpy as np
from PIL import Image

from .region_postprocess import build_label_map, fill_small_holes, filter_components, region_records, resolve_exclusive_masks, validate_partition
from .region_schema import EXCLUSIVE_LABELS, SEMANTIC_REGION_VERSION


BACKEND = "heuristic_anime_v1"


def generate_heuristic_anime_proposal(image_path, options=None):
    options = options or {}; path = Path(image_path)
    rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8); rgb = rgba[:, :, :3]; alpha = rgba[:, :, 3]
    h, w = alpha.shape; warnings = []; diagnostics = {}
    foreground, fg_source = _foreground(rgb, alpha, int(options.get("foreground_alpha_threshold", 8)))
    foreground = fill_small_holes(filter_components(foreground, int(options.get("minimum_region_area", 12))), 24)
    clusters, centers = _quantize(rgb, foreground, int(options.get("color_clusters", 12)))
    diagnostics.update({"foreground_source": fg_source, "color_cluster_centers_rgb": centers, "color_cluster_count": len(centers)})
    masks, confidences = _semantic_masks(rgb, foreground, clusters, centers)
    _apply_hints(masks, confidences, options.get("region_hints"), w, h, warnings)
    exclusive = resolve_exclusive_masks(masks, foreground)
    outline = _outline_mask(foreground, rgb)
    label_map = build_label_map(exclusive)
    confidence_map = np.zeros((h, w), dtype=np.float32)
    for label, mask in exclusive.items(): confidence_map[mask] = confidences.get(label, 1.0 if label == "background" else 0.3)
    fg_count = int(foreground.sum()); unknown = int(exclusive["foreground_unknown"].sum())
    unknown_ratio = unknown / max(1, fg_count)
    if unknown_ratio > float(options.get("unknown_warning_threshold", 0.65)): warnings.append("Foreground unknown ratio is high; semantic proposal is intentionally conservative.")
    records = region_records(exclusive, confidences, fg_count, BACKEND)
    coverage = {"foreground_pixel_count": fg_count, "classified_foreground_pixel_count": fg_count - unknown,
        "foreground_unknown_pixel_count": unknown, "foreground_unknown_ratio": round(unknown_ratio, 6),
        "background_pixel_count": int((~foreground).sum()), "exclusive_partition_valid": validate_partition(exclusive, foreground)}
    status = "completed_with_warnings" if warnings else "completed"
    return {"semantic_region_version": SEMANTIC_REGION_VERSION, "status": status, "backend": BACKEND,
        "image_path": str(path), "image_size": {"width": w, "height": h}, "labels": list(EXCLUSIVE_LABELS),
        "regions": records, "coverage": coverage,
        "confidence_summary": {label: round(float(confidences.get(label, 0.0)), 4) for label in EXCLUSIVE_LABELS},
        "diagnostics": diagnostics, "warnings": warnings,
        "_masks": {**exclusive, "outline_edge": outline}, "_label_map": label_map, "_confidence_map": confidence_map}


def _foreground(rgb, alpha, threshold):
    meaningful = int((alpha < 250).sum()) > alpha.size * 0.01 and int((alpha > threshold).sum()) > 0
    if meaningful: return alpha > threshold, "source_alpha"
    border = np.concatenate((rgb[0], rgb[-1], rgb[:,0], rgb[:,-1]), axis=0).astype(np.float32)
    bg = np.median(border, axis=0); distance = np.sqrt(((rgb.astype(np.float32)-bg) ** 2).sum(axis=2))
    threshold_value = max(18.0, float(np.percentile(np.sqrt(((border-bg)**2).sum(axis=1)), 90)) + 10.0)
    return distance > threshold_value, "border_color_separation"


def _quantize(rgb, foreground, count):
    image = Image.fromarray(rgb, "RGB"); quantized = image.quantize(colors=max(2, min(32, count)), method=Image.Quantize.MEDIANCUT)
    labels = np.asarray(quantized, dtype=np.int16); palette = quantized.getpalette(); centers = []
    for index in sorted(int(value) for value in np.unique(labels[foreground])):
        centers.append({"cluster_id": index, "rgb": palette[index*3:index*3+3], "pixel_count": int(((labels==index)&foreground).sum())})
    return labels, centers


def _semantic_masks(rgb, foreground, clusters, centers):
    h,w = foreground.shape; yy,xx = np.indices((h,w)); ys,xs = np.where(foreground)
    if len(xs) == 0: return {}, {"background": 1.0, "foreground_unknown": 1.0}
    x0,x1,y0,y1 = xs.min(),xs.max()+1,ys.min(),ys.max()+1; fw=max(1,x1-x0); fh=max(1,y1-y0)
    upper = yy < y0 + fh*.62; lower = yy > y0 + fh*.43
    r,g,b = [rgb[:,:,i].astype(np.float32) for i in range(3)]
    maximum=np.maximum.reduce([r,g,b]); minimum=np.minimum.reduce([r,g,b]); saturation=(maximum-minimum)/(maximum+1)
    skin_color = (r > 105) & (r >= g*.92) & (r >= b*.9) & ((r-b)>5) & (saturation < .48)
    skin_candidates = filter_components(foreground & skin_color, max(8, int(foreground.sum()*.001)), False)
    face_zone = (xx > x0+fw*.18)&(xx<x0+fw*.82)&(yy>y0+fh*.08)&(yy<y0+fh*.62)
    face = skin_candidates & face_zone
    face_conf = min(.78, .3 + face.sum()/max(1, foreground.sum())*4) if face.sum() >= 12 else .2
    if face_conf < .42: face[:] = False
    body_skin = skin_candidates & ~face & lower
    # Hair is upper foreground adjacent to face; no dark-color assumption.
    expanded_face = _dilate(face, max(2, int(min(fw,fh)*.08))) if face.any() else np.zeros_like(face)
    hair = foreground & upper & ~skin_candidates & (expanded_face | (yy < y0+fh*.38))
    hair = filter_components(hair, max(8,int(foreground.sum()*.002)), True)
    # Compact high-contrast components in the upper half of a confident face.
    gray = rgb.mean(axis=2); local_dark = gray < np.percentile(gray[face], 35) if face.any() else np.zeros_like(face)
    eye_zone = face & (yy < y0+fh*.43) & (yy > y0+fh*.16)
    eyes = np.zeros_like(face)
    if face_conf >= .42:
        for component in __import__("engine.vision.semantic_regions.region_postprocess", fromlist=["connected_components"]).connected_components(eye_zone & local_dark):
            cy,cx = zip(*component); bw=max(cx)-min(cx)+1; bh=max(cy)-min(cy)+1
            if 2 <= len(component) <= max(6,int(face.sum()*.08)) and bw <= fw*.22 and bh <= fh*.13:
                eyes[np.array(cy),np.array(cx)] = True
    mouth_zone = face & (yy > y0+fh*.34) & (yy < y0+fh*.58)
    reddish = (r > g*1.08) & (r > b*1.03) & (saturation > .12)
    mouth = filter_components(mouth_zone & reddish, 2, False)
    if mouth.sum() > max(20, face.sum()*.05): mouth[:] = False
    reserved = face | body_skin | hair | eyes | mouth
    clothing = filter_components(foreground & lower & ~reserved, max(12,int(foreground.sum()*.003)), True)
    return {"hair": hair, "face_skin": face, "eyes": eyes, "mouth": mouth, "body_skin": body_skin, "clothing": clothing}, {
        "background": .98, "foreground_unknown": .3, "face_skin": face_conf,
        "body_skin": .5 if body_skin.any() else .2, "hair": .58 if hair.any() else .25,
        "eyes": .62 if eyes.any() else .15, "mouth": .52 if mouth.any() else .12,
        "clothing": .55 if clothing.any() else .25,
    }


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
