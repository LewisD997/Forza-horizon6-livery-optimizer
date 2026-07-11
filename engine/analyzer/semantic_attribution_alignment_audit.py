import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

from .shape_visibility_analyzer import iter_visible_shape_masks


def audit_semantic_attribution_alignment(geometry,source_image_path,attribution,options=None):
    options=options or {}; source=Image.open(source_image_path).convert("RGBA"); width,height=source.size; source_fg=np.asarray(source)[:,:,3]>0
    geometry_size=options.get("geometry_render_size") or {"width":width,"height":height}; warnings=[]
    identity=geometry_size.get("width")==width and geometry_size.get("height")==height
    transform={"scale_x":width/max(1,geometry_size.get("width",width)),"scale_y":height/max(1,geometry_size.get("height",height)),"translate_x":0.0,"translate_y":0.0}
    if not identity: warnings.append("Geometry/source dimensions differ; scale transform is required and attribution should be reviewed.")
    union=np.zeros((height,width),dtype=bool)
    for _,_,visible in iter_visible_shape_masks(geometry,width,height,1.0):
        if visible is not None: union|=visible>1e-5
    on_background=union&~source_fg; visible_count=int(union.sum()); background_primary=sum(item.get("primary_region")=="background" and item.get("shape_index")!=0 for item in attribution["layers"])
    ratio=float(on_background.sum()/max(1,visible_count))
    confidence="high" if identity and ratio<.08 else ("medium" if ratio<.2 else "low")
    return {"alignment_audit_version":"0.7.0.2","alignment_method":"identity_source_canvas" if identity else "explicit_scale_to_source",
        "source_size":{"width":width,"height":height},"geometry_render_size":geometry_size,"transform":transform,
        "visible_geometry_pixel_count":visible_count,"visible_geometry_on_background_pixel_count":int(on_background.sum()),
        "visible_geometry_on_background_ratio":round(ratio,8),"source_foreground_without_geometry_count":int((source_fg&~union).sum()),
        "background_primary_shape_count":background_primary,"alignment_confidence":confidence,"warnings":warnings}


def write_background_attribution_review(attribution,source_image_path,output_dir,overwrite=False,limit=50):
    output=Path(output_dir); suspects=[item for item in attribution["layers"] if item.get("shape_index")!=0 and item.get("primary_region")=="background" and item.get("attribution_status") not in {"fully_occluded","unsupported"}]
    suspects=sorted(suspects,key=lambda item:item.get("estimated_visible_alpha_area",0),reverse=True)[:limit]
    rows=[{"shape_index":item["shape_index"],"shape_uid":item["shape_uid"],"visible_area":item["estimated_visible_alpha_area"],
        "background_overlap_ratio":item.get("all_region_overlaps",{}).get("background",0),"foreground_overlap_ratio":round(1-item.get("all_region_overlaps",{}).get("background",0),6),
        "transformed_bbox":None,"likely_cause":"geometry_extends_outside_source_alpha_or_alignment"} for item in suspects]
    report={"background_review_version":"0.7.0.2","suspect_count":len(rows),"base_shape_excluded":True,"fully_occluded_excluded":True,"items":rows}
    _write_json(report,output/"background_attribution_review.json",overwrite)
    csv_path=output/"background_attribution_review.csv"; _guard(csv_path,overwrite)
    with csv_path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]) if rows else ["shape_index","shape_uid","visible_area","background_overlap_ratio","foreground_overlap_ratio","transformed_bbox","likely_cause"]);writer.writeheader();writer.writerows(rows)
    image=Image.open(source_image_path).convert("RGB"); image.thumbnail((700,700)); sheet=Image.new("RGB",(900,max(420,image.height+80)),"white");sheet.paste(image,(10,50));draw=ImageDraw.Draw(sheet);draw.text((10,10),"Background Attribution Review - base shape excluded",fill="black")
    y=50
    for row in rows[:30]: draw.text((720,y),f"#{row['shape_index']} bg={row['background_overlap_ratio']:.3f}",fill="black");y+=16
    sheet_path=output/"background_attribution_review_sheet.png";_guard(sheet_path,overwrite);sheet.save(sheet_path)
    return report


def _write_json(data,path,overwrite): _guard(path,overwrite);path.write_text(json.dumps(data,indent=2),encoding="utf-8")
def _guard(path,overwrite):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and not overwrite: raise FileExistsError(path)
