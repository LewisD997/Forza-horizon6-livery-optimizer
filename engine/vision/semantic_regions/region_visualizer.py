from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .region_schema import PALETTE, REGION_IDS


def write_region_visualizations(result, output_dir, attribution=None, overwrite=False):
    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True); source=Image.open(result["image_path"]).convert("RGBA")
    masks=result["_masks"]; label_map=result["_label_map"]; confidence=result["_confidence_map"]
    paths={"region_map":output/"semantic_region_map.png","overlay":output/"semantic_region_overlay.png","confidence":output/"semantic_region_confidence.png",
        "review_sheet":output/"semantic_region_review_sheet.png","attribution_overlay":output/"layer_attribution_overlay.png",
        "alpha_guardrail":output/"semantic_alpha_guardrail.png"}
    region_image=Image.fromarray(label_map.astype("uint8"),"P")
    palette=[]
    for index in range(256):
        label=next((name for name,value in REGION_IDS.items() if value==index),"unknown"); palette.extend(PALETTE[label])
    region_image.putpalette(palette); _save(region_image,paths["region_map"],overwrite)
    overlay=Image.blend(source.convert("RGB"),region_image.convert("RGB"),.42); overlay=_with_legend(overlay); _save(overlay,paths["overlay"],overwrite)
    conf=Image.fromarray(np.clip(confidence*255,0,255).astype("uint8"),"L"); _save(conf,paths["confidence"],overwrite)
    domain=np.asarray(result.get("_semantic_domain",~masks["background"]),dtype=bool)
    leaks=np.zeros_like(domain)
    for label,mask in masks.items():
        if label not in {"background","outline_edge"}: leaks|=mask&~domain
    guard=np.zeros((*domain.shape,3),dtype=np.uint8); guard[domain]=(185,185,185); guard[leaks]=(255,0,40)
    guard_image=Image.fromarray(guard,"RGB"); _save(guard_image,paths["alpha_guardrail"],overwrite)
    mask_dir=output/"region_masks"; mask_dir.mkdir(exist_ok=True)
    mask_paths={}
    for label,mask in masks.items():
        path=mask_dir/f"{label}.png"; _save(Image.fromarray(mask.astype("uint8")*255,"L"),path,overwrite); mask_paths[label]=str(path)
    review=_review_sheet(source,region_image.convert("RGB"),overlay,conf,guard_image,result,masks,domain); _save(review,paths["review_sheet"],overwrite)
    if attribution is not None: _save(_attribution_overlay(overlay,attribution),paths["attribution_overlay"],overwrite)
    return {key:str(value) for key,value in paths.items() if value.exists()},mask_paths


def _with_legend(image):
    canvas=Image.new("RGB",(image.width+190,image.height),"white"); canvas.paste(image,(0,0)); draw=ImageDraw.Draw(canvas); y=12
    for label,color in PALETTE.items(): draw.rectangle((image.width+10,y,image.width+28,y+14),fill=color); draw.text((image.width+34,y),label,fill="black"); y+=20
    return canvas


def _review_sheet(source,region_map,overlay,confidence,guard,result,masks,domain):
    tiles=[]
    alpha=Image.fromarray(domain.astype("uint8")*255,"L").convert("RGB")
    for image in (source.convert("RGB"),alpha,region_map,overlay,confidence.convert("RGB"),guard):
        tile=image.copy(); tile.thumbnail((240,180)); tiles.append(tile)
    sheet=Image.new("RGB",(1000,650),"white"); draw=ImageDraw.Draw(sheet); draw.text((10,8),f"FLO Semantic Region Proposal - {result['backend']}",fill="black")
    for i,(label,image) in enumerate(zip(("source","strict foreground","map","overlay","confidence","alpha guardrail"),tiles)):
        x=10+(i%4)*245; y=52+(i//4)*220; draw.text((x,y-18),label,fill="black"); sheet.paste(image,(x,y))
    y=500; coverage=result["coverage"]
    draw.text((10,y),f"foreground={coverage['foreground_pixel_count']} background={coverage['background_pixel_count']} unknown_ratio={coverage['foreground_unknown_ratio']}",fill="black"); y+=22
    eye=(result.get("diagnostics") or {}).get("eye_detection") or {}
    draw.text((10,y),f"transparent_leaks={coverage.get('transparent_semantic_leak_count')} eye_to_face={eye.get('eye_to_face_area_ratio')}",fill="black"); y+=22
    for record in result["regions"]: draw.text((10,y),f"{record['label']}: area={record['pixel_area']} confidence={record['confidence']} ({record['confidence_level']})",fill="black"); y+=18
    for warning in result["warnings"][:5]: draw.text((580,y),warning,fill=(170,30,30)); y+=18
    return sheet


def _attribution_overlay(base,attribution):
    image=base.copy(); draw=ImageDraw.Draw(image); shown=0
    for item in sorted(attribution["layers"],key=lambda value:value["estimated_visible_alpha_area"],reverse=True):
        if item["attribution_status"] not in {"assigned","ambiguous"}: continue
        # Representative IDs only; precise per-shape bbox is in visibility metadata.
        x=12+(shown%4)*150; y=image.height-22-(shown//4)*18; draw.text((x,y),f"#{item['shape_index']} {item['primary_region']}",fill="white",stroke_width=2,stroke_fill="black"); shown+=1
        if shown>=12: break
    return image


def _save(image,path,overwrite):
    if path.exists() and not overwrite: raise FileExistsError(path)
    image.save(path)
