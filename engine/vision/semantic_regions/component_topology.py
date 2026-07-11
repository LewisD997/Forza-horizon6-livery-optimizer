import math

import numpy as np

from .region_postprocess import bbox_for_mask, connected_components


def build_component_topology(rgb, cluster_map, domain, gap=2, minimum_component_area=4):
    nodes=[]; node_id=0; suppressed=0; suppressed_pixels=0
    for cluster_id in sorted(int(value) for value in np.unique(cluster_map[domain])):
        for points in connected_components((cluster_map==cluster_id)&domain):
            if not points: continue
            if len(points)<minimum_component_area: suppressed+=1; suppressed_pixels+=len(points); continue
            ys,xs=zip(*points); mask=np.zeros(domain.shape,dtype=bool); mask[np.array(ys),np.array(xs)]=True
            colors=rgb[mask].astype(np.float32); bbox=bbox_for_mask(mask)
            nodes.append({"component_id":f"component_{node_id:05d}","cluster_id":cluster_id,"pixel_count":len(points),"bbox":bbox,
                "centroid":{"x":round(float(np.mean(xs)),3),"y":round(float(np.mean(ys)),3)},"mean_color":[round(float(v),3) for v in colors.mean(axis=0)],
                "median_color":[int(v) for v in np.median(colors,axis=0)],"foreground_boundary_contact":_boundary_contact(mask,domain),
                "candidate_semantic_labels":[],"confidence":0.0,"_mask":mask}); node_id+=1
    edges=[]
    ordered=sorted(nodes,key=lambda node:node["bbox"]["x"])
    for i,left in enumerate(ordered):
        left_right=left["bbox"]["x"]+left["bbox"]["width"]
        for right in ordered[i+1:]:
            if right["bbox"]["x"]>left_right+gap: break
            distance=_bbox_gap(left["bbox"],right["bbox"])
            if distance>gap: continue
            color_distance=math.sqrt(sum((a-b)**2 for a,b in zip(left["mean_color"],right["mean_color"])))
            if distance==0 or color_distance<=55:
                edges.append({"source":left["component_id"],"target":right["component_id"],"gap":distance,"color_distance":round(color_distance,3),"boundary_length":_contact_length(left["_mask"],right["_mask"],gap)})
    return {"component_count":len(nodes),"edge_count":len(edges),"nodes":nodes,"edges":edges,"gap":gap,
        "minimum_component_area":minimum_component_area,"suppressed_tiny_component_count":suppressed,"suppressed_tiny_pixel_count":suppressed_pixels}


def public_topology(topology):
    return {**topology,"nodes":[{key:value for key,value in node.items() if not key.startswith("_")} for node in topology["nodes"]]}


def neighbors(topology,component_id):
    ids=[]
    for edge in topology["edges"]:
        if edge["source"]==component_id: ids.append(edge["target"])
        elif edge["target"]==component_id: ids.append(edge["source"])
    by_id={node["component_id"]:node for node in topology["nodes"]}
    return [by_id[item] for item in ids]


def _bbox_gap(a,b):
    ax1=a["x"]+a["width"]; ay1=a["y"]+a["height"]; bx1=b["x"]+b["width"]; by1=b["y"]+b["height"]
    dx=max(0,a["x"]-bx1,b["x"]-ax1); dy=max(0,a["y"]-by1,b["y"]-ay1); return max(dx,dy)


def _boundary_contact(mask,domain):
    h,w=mask.shape; p=np.pad(domain,1,constant_values=False); interior=p[:-2,1:w+1]&p[2:,1:w+1]&p[1:h+1,:-2]&p[1:h+1,2:]
    return int((mask&~interior).sum())


def _contact_length(left,right,gap):
    expanded=np.array(left,copy=True); h,w=left.shape
    for _ in range(max(1,gap+1)):
        p=np.pad(expanded,1); expanded=p[:-2,1:w+1]|p[2:,1:w+1]|p[1:h+1,:-2]|p[1:h+1,2:]|expanded
    return int((expanded&right).sum())
