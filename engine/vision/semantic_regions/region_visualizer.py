from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .region_schema import PALETTE, REGION_IDS


def write_region_visualizations(result, output_dir, attribution=None, overwrite=False):
    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True); source=Image.open(result["image_path"]).convert("RGBA")
    masks=result["_masks"]; label_map=result["_label_map"]; confidence=result["_confidence_map"]
    paths={"region_map":output/"semantic_region_map.png","overlay":output/"semantic_region_overlay.png","confidence":output/"semantic_region_confidence.png",
        "review_sheet":output/"semantic_region_review_sheet.png","attribution_overlay":output/"layer_attribution_overlay.png"}
    region_image=Image.fromarray(label_map.astype("uint8"),"P")
    palette=[]
    for index in range(256):
        label=next((name for name,value in REGION_IDS.items() if value==index),"unknown"); palette.extend(PALETTE[label])
    region_image.putpalette(palette); _save(region_image,paths["region_map"],overwrite)
    overlay=Image.blend(source.convert("RGB"),region_image.convert("RGB"),.42); overlay=_with_legend(overlay); _save(overlay,paths["overlay"],overwrite)
    conf=Image.fromarray(np.clip(confidence*255,0,255).astype("uint8"),"L"); _save(conf,paths["confidence"],overwrite)
    mask_dir=output/"region_masks"; mask_dir.mkdir(exist_ok=True)
    mask_paths={}
    for label,mask in masks.items():
        path=mask_dir/f"{label}.png"; _save(Image.fromarray(mask.astype("uint8")*255,"L"),path,overwrite); mask_paths[label]=str(path)
    review=_review_sheet(source,region_image.convert("RGB"),overlay,conf,result,masks); _save(review,paths["review_sheet"],overwrite)
    if attribution is not None: _save(_attribution_overlay(overlay,attribution),paths["attribution_overlay"],overwrite)
    return {key:str(value) for key,value in paths.items() if value.exists()},mask_paths


def _with_legend(image):
    canvas=Image.new("RGB",(image.width+190,image.height),"white"); canvas.paste(image,(0,0)); draw=ImageDraw.Draw(canvas); y=12
    for label,color in PALETTE.items(): draw.rectangle((image.width+10,y,image.width+28,y+14),fill=color); draw.text((image.width+34,y),label,fill="black"); y+=20
    return canvas


def _review_sheet(source,region_map,overlay,confidence,result,masks):
    tiles=[]
    for image in (source.convert("RGB"),region_map,overlay,confidence.convert("RGB")):
        tile=image.copy(); tile.thumbnail((280,220)); tiles.append(tile)
    sheet=Image.new("RGB",(1160,520),"white"); draw=ImageDraw.Draw(sheet); draw.text((10,8),f"FLO Semantic Region Proposal - {result['backend']}",fill="black")
    for x,label,image in zip((10,295,580,865),("source","map","overlay","confidence"),tiles): draw.text((x,32),label,fill="black"); sheet.paste(image,(x,52))
    y=290; coverage=result["coverage"]
    draw.text((10,y),f"foreground={coverage['foreground_pixel_count']} background={coverage['background_pixel_count']} unknown_ratio={coverage['foreground_unknown_ratio']}",fill="black"); y+=22
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
