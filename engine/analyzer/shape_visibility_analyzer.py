import copy

import numpy as np
from PIL import Image, ImageDraw

from engine.optimizer.change_plan import make_shape_uid
from engine.renderer import paint_studio_source_renderer as renderer


def rasterize_shape_alpha(shape, width, height, scale=1.0):
    target_w=max(1,int(round(width*scale))); target_h=max(1,int(round(height*scale)))
    data=shape.get("data") if isinstance(shape.get("data"),list) else []; shape_type=int(shape.get("type",-1)); coverage=None
    scaled=_scale_data(data,shape_type,scale)
    if shape_type==1 and len(scaled)>=4: coverage=renderer._axis_rect_coverage(scaled,target_w,target_h,1,np)
    elif shape_type==2 and len(scaled)>=4: coverage=renderer._rotated_rect_coverage(scaled,target_w,target_h,1,np)
    elif shape_type in {16,0xE2,0xE4} and len(scaled)>=4: coverage=renderer._rotated_ellipse_coverage(scaled,target_w,target_h,1,np)
    elif shape_type==32 and len(scaled)>=6: coverage=renderer._triangle_coverage(scaled,target_w,target_h,1,Image,ImageDraw,np)
    if coverage is None: return None
    mask=np.zeros((target_h,target_w),dtype=np.float32); local=coverage["mask"]
    y,x=coverage["y0"],coverage["x0"]; mask[y:y+local.shape[0],x:x+local.shape[1]]=local
    alpha=(shape.get("color") or [0,0,0,255]); alpha_value=float(alpha[3])/255 if len(alpha)>=4 else 1.0
    return mask*max(0,min(1,alpha_value))


def analyze_shape_visibility(geometry, canvas_width, canvas_height, options=None):
    options=options or {}; scale=float(options.get("visibility_resolution_scale",1.0)); shapes=geometry.get("shapes",[])
    h=max(1,int(round(canvas_height*scale))); w=max(1,int(round(canvas_width*scale))); remaining=np.ones((h,w),dtype=np.float32)
    results=[None]*len(shapes); warnings=[]
    for index in range(len(shapes)-1,-1,-1):
        shape=shapes[index]; mask=rasterize_shape_alpha(shape,canvas_width,canvas_height,scale)
        if mask is None:
            results[index]=_entry(shape,index,0,0,None,"unsupported",[f"Unsupported shape type: {shape.get('type')}"]); warnings.extend(results[index]["warnings"]); continue
        visible=mask*remaining; total=float(mask.sum()); visible_area=float(visible.sum()); bbox=_bbox(visible)
        results[index]=_entry(shape,index,total,visible_area,bbox,"rendered",[])
        remaining*=1-mask
    return {"shape_visibility_version":"0.7.0","status":"completed_with_warnings" if warnings else "completed",
        "canvas":{"width":canvas_width,"height":canvas_height,"resolution_scale":scale},"shape_count":len(shapes),"shapes":results,"warnings":warnings}


def iter_visible_shape_masks(geometry,width,height,scale=1.0):
    shapes=geometry.get("shapes",[]); h=max(1,int(round(height*scale))); w=max(1,int(round(width*scale))); remaining=np.ones((h,w),dtype=np.float32)
    for index in range(len(shapes)-1,-1,-1):
        mask=rasterize_shape_alpha(shapes[index],width,height,scale)
        visible=None if mask is None else mask*remaining
        if mask is not None: remaining*=1-mask
        yield index, mask, visible


def _entry(shape,index,total,visible,bbox,status,warnings):
    occluded=max(0,total-visible); ratio=occluded/max(total,1e-9) if total else 1.0
    return {"shape_index":index,"shape_uid":make_shape_uid(shape,index),"shape_type":shape.get("type"),
        "total_alpha_area":round(total,6),"estimated_visible_alpha_area":round(visible,6),
        "estimated_occluded_alpha_area":round(occluded,6),"estimated_occlusion_ratio":round(min(1,ratio),6),
        "visible_bbox":bbox,"rasterization_status":status,"warnings":warnings}


def _scale_data(data,shape_type,scale):
    result=copy.deepcopy(data)
    limit=6 if shape_type==32 else min(4,len(result))
    for i in range(limit): result[i]=float(result[i])*scale
    return result


def _bbox(mask):
    ys,xs=np.where(mask>1e-5)
    if not len(xs): return None
    x0,y0,x1,y1=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
    return {"x":x0,"y":y0,"width":x1-x0,"height":y1-y0}
