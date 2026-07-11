import copy,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.analyzer.layer_region_attribution import attribute_layers_to_semantic_regions
from engine.analyzer.layer_region_attribution import _attribute
from engine.analyzer.shape_visibility_analyzer import analyze_shape_visibility
from engine.analyzer.semantic_attribution_alignment_audit import audit_semantic_attribution_alignment
from engine.vision.semantic_regions.region_backend import generate_semantic_region_proposal
from engine.vision.semantic_regions.region_postprocess import validate_partition
from engine.vision.semantic_regions.stripe_diagnostics import analyze_semantic_stripes
from scripts.generate_semantic_region_map import run_from_args
from scripts.validate_semantic_region_map import validate_outputs


def main():
    test_foreground_and_determinism(); test_strict_alpha_guardrails(); test_eye_guardrails()
    test_visibility_and_attribution(); test_stripe_and_sensitive_guardrails(); test_alignment_warning(); test_cli_validation(); test_corrupted_map_fails()
    print("Semantic region map tests passed."); return 0


def test_foreground_and_determinism():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); transparent=root/"transparent.png"; image=Image.new("RGBA",(60,80),(0,0,0,0)); ImageDraw.Draw(image).rectangle((15,10,45,70),fill=(200,80,120,255)); image.save(transparent)
        a=generate_semantic_region_proposal(str(transparent)); b=generate_semantic_region_proposal(str(transparent))
        assert a["diagnostics"]["foreground_source"]=="source_alpha_strict" and np.array_equal(a["_label_map"],b["_label_map"])
        assert validate_partition(a["_masks"],~a["_masks"]["background"])
        opaque=root/"opaque.png"; _anime_image().convert("RGB").save(opaque); result=generate_semantic_region_proposal(str(opaque))
        assert result["diagnostics"]["foreground_source"]=="border_color_separation"
        assert result["coverage"]["foreground_unknown_pixel_count"]>=0
        assert any(record["label"] in {"hair","face_skin","clothing","foreground_unknown"} for record in result["regions"])


def test_strict_alpha_guardrails():
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/"alpha.png"; array=np.zeros((8,10,4),dtype=np.uint8)
        array[:,:,:3]=[71,203,119]; array[:,:,3]=0; array[2:6,2:8,:3]=[220,170,140]; array[2:6,2:8,3]=1
        Image.fromarray(array,"RGBA").save(path); result=generate_semantic_region_proposal(str(path),{"foreground_alpha_threshold":0,"minimum_region_area":1})
        coverage=result["coverage"]; diagnostics=result["diagnostics"]
        assert diagnostics["foreground_extraction"]["mode"]=="source_alpha_strict"
        assert coverage["foreground_pixel_count"]==24 and coverage["background_pixel_count"]==56
        assert coverage["source_transparent_pixel_count"]==56 and coverage["source_nontransparent_pixel_count"]==24
        assert coverage["transparent_semantic_leak_count"]==0 and coverage["transparent_background_recall"]==1.0
        assert coverage["clustered_background_pixel_count"]==0
        assert diagnostics["color_clustering"]["cluster_pixel_total"]==24
        for label,mask in result["_masks"].items():
            if label not in {"background","outline_edge"}: assert not mask[array[:,:,3]==0].any()


def test_eye_guardrails():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        valid=_anime_image(); valid.putalpha(255); valid_path=root/"valid.png"; valid.save(valid_path)
        valid_result=generate_semantic_region_proposal(str(valid_path),{"minimum_region_area":1})
        eye=valid_result["diagnostics"]["eye_detection"]
        assert eye["eye_mask_area"] <= max(1,int(next((r["pixel_area"] for r in valid_result["regions"] if r["label"]=="face_skin"),1)*.05))
        oversized=_anime_image(); draw=ImageDraw.Draw(oversized); draw.rectangle((10,8,29,18),fill=(10,10,10,255)); large=root/"large.png"; oversized.save(large)
        large_eye=generate_semantic_region_proposal(str(large),{"minimum_region_area":1})["diagnostics"]["eye_detection"]
        assert large_eye["eye_mask_area"]==0 or any("area_too_large" in item["reasons"] or "bbox_too_large" in item["reasons"] for item in large_eye["rejected_candidates"])


def test_visibility_and_attribution():
    geometry=_geometry(); original=copy.deepcopy(geometry); visibility=analyze_shape_visibility(geometry,40,30)
    assert visibility["shapes"][1]["estimated_visible_alpha_area"] < visibility["shapes"][1]["total_alpha_area"]
    assert visibility["shapes"][3]["estimated_visible_alpha_area"]==0
    masks={label:np.zeros((30,40),dtype=bool) for label in ("background","hair","face_skin","eyes","mouth","body_skin","clothing","foreground_unknown","outline_edge")}
    masks["background"][:]=True; masks["face_skin"][5:25,5:20]=True; masks["eyes"][10:15,15:25]=True; masks["clothing"][5:25,20:35]=True; masks["background"][5:25,5:35]=False
    semantic={"_masks":masks,"regions":[_record("background",900),_record("face_skin",275),_record("eyes",50),_record("clothing",300)]}
    attribution=attribute_layers_to_semantic_regions(geometry,semantic,visibility,{"attribution_overlap_threshold":.05})
    assert len(attribution["layers"])==len(geometry["shapes"]) and geometry==original
    assert attribution["layers"][2]["secondary_regions"]
    assert attribution["layers"][2]["sensitive_region"] is True
    assert attribution["layers"][3]["attribution_status"]=="fully_occluded" and not attribution["layers"][3]["sensitive_region"]


def test_stripe_and_sensitive_guardrails():
    label_map=np.zeros((30,40),dtype=np.uint8); domain=np.ones((30,40),dtype=bool); label_map[:10]=1; label_map[10:20]=2; label_map[20:]=6
    stripes=analyze_semantic_stripes(label_map,domain,.5); assert stripes["suspicious_horizontal_transition_count"]==2 and stripes["affected_rows"]==[10,20]
    visible=np.ones((10,10),dtype=np.float32); visibility={"total_alpha_area":100,"estimated_visible_alpha_area":100,"estimated_occlusion_ratio":0}
    masks={label:np.zeros((10,10),dtype=np.float32) for label in ("background","hair","face_skin","eyes","mouth","body_skin","clothing","foreground_unknown","outline_edge","face_core")}
    masks["clothing"][:]=1; masks["face_core"][0,0]=1
    tiny=_attribute({"type":1},1,visible,visibility,masks,.05,.08); assert not tiny["sensitive_region"]
    masks["eyes"][0:2,0:5]=1; meaningful=_attribute({"type":1},1,visible,visibility,masks,.05,.08); assert meaningful["sensitive_region"] and meaningful["sensitive_triggers"]
    masks["eyes"][:]=0; masks["outline_edge"][0:2,:]=1; outline=_attribute({"type":1},1,visible,visibility,masks,.05,.08); assert not outline["sensitive_region"] and outline["sensitive_boundary"]


def test_alignment_warning():
    with tempfile.TemporaryDirectory() as temp:
        source=Path(temp)/"source.png"; Image.new("RGBA",(40,30),(0,0,0,0)).save(source)
        attribution={"layers":[]}; audit=audit_semantic_attribution_alignment(_geometry(),str(source),attribution,{"geometry_render_size":{"width":20,"height":15}})
        assert audit["alignment_method"]=="explicit_scale_to_source" and audit["warnings"]


def test_cli_validation():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); image=root/"source.png"; _anime_image().save(image); geometry=root/"geometry.json"; geometry.write_text(json.dumps(_geometry()),encoding="utf-8")
        args=SimpleNamespace(case=None,image=str(image),geometry=str(geometry),plan=None,visible_contribution_report=None,output_dir=str(root/"out"),backend="heuristic-anime",region_hints=None,
            foreground_alpha_threshold=8,color_clusters=8,minimum_region_area=4,unknown_warning_threshold=.9,attribution_overlap_threshold=.05,ambiguity_margin=.08,visibility_resolution_scale=1.0,
            debug_shape_indexes=None,overwrite=False,skip_layer_attribution=False,no_visualizations=True)
        result=run_from_args(args); validate_outputs(_public_regions(result["regions"]),result["attribution"],_geometry())


def test_corrupted_map_fails():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); image=root/"source.png"; rgba=np.zeros((30,40,4),dtype=np.uint8); rgba[5:25,8:32]=[200,120,150,255]; Image.fromarray(rgba,"RGBA").save(image)
        geometry=root/"geometry.json"; geometry.write_text(json.dumps(_geometry()),encoding="utf-8")
        args=SimpleNamespace(case=None,image=str(image),geometry=str(geometry),plan=None,visible_contribution_report=None,output_dir=str(root/"out"),backend="heuristic-anime",region_hints=None,
            foreground_alpha_threshold=0,color_clusters=8,minimum_region_area=1,unknown_warning_threshold=.9,attribution_overlap_threshold=.05,ambiguity_margin=.08,visibility_resolution_scale=1.0,
            debug_shape_indexes=None,overwrite=False,skip_layer_attribution=False,no_visualizations=False)
        result=run_from_args(args); map_path=Path(result["regions"]["outputs"]["region_map"]); region_map=Image.open(map_path); values=np.array(region_map); values[0,0]=1
        corrupted=Image.fromarray(values.astype("uint8"),"P"); corrupted.putpalette(region_map.getpalette()); corrupted.save(map_path)
        try: validate_outputs(_public_regions(result["regions"]),result["attribution"],_geometry())
        except ValueError as exc: assert "source-transparent" in str(exc)
        else: raise AssertionError("Validator accepted a semantic label in transparent background.")


def _anime_image():
    image=Image.new("RGBA",(40,30),(245,245,245,255)); draw=ImageDraw.Draw(image); draw.rectangle((8,2,31,9),fill=(120,80,190,255)); draw.rectangle((10,7,29,20),fill=(235,180,145,255)); draw.rectangle((13,11,16,13),fill=(30,30,50,255)); draw.rectangle((23,11,26,13),fill=(30,30,50,255)); draw.rectangle((17,17,21,18),fill=(180,70,80,255)); draw.rectangle((7,20,32,29),fill=(50,110,190,255)); return image
def _geometry(): return {"shapes":[
    {"type":1,"data":[0,0,40,30],"color":[255,255,255,255],"score":0},
    {"type":1,"data":[5,5,30,20],"color":[200,100,100,255],"score":.1},
    {"type":1,"data":[15,5,20,20],"color":[50,50,100,200],"score":.2},
    {"type":1,"data":[16,10,4,4],"color":[0,0,0,255],"score":.3},
    {"type":1,"data":[16,10,4,4],"color":[255,255,255,255],"score":.4}]}
def _record(label,area): return {"label":label,"confidence":.7,"pixel_area":area}
def _public_regions(result): return {k:v for k,v in result.items() if not k.startswith("_")}
if __name__=="__main__": raise SystemExit(main())
