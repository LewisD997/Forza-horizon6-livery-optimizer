import copy,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from engine.analyzer.layer_region_attribution import attribute_layers_to_semantic_regions
from engine.analyzer.shape_visibility_analyzer import analyze_shape_visibility
from engine.vision.semantic_regions.region_backend import generate_semantic_region_proposal
from engine.vision.semantic_regions.region_postprocess import validate_partition
from scripts.generate_semantic_region_map import run_from_args
from scripts.validate_semantic_region_map import validate_outputs


def main():
    test_foreground_and_determinism(); test_visibility_and_attribution(); test_cli_validation()
    print("Semantic region map tests passed."); return 0


def test_foreground_and_determinism():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); transparent=root/"transparent.png"; image=Image.new("RGBA",(60,80),(0,0,0,0)); ImageDraw.Draw(image).rectangle((15,10,45,70),fill=(200,80,120,255)); image.save(transparent)
        a=generate_semantic_region_proposal(str(transparent)); b=generate_semantic_region_proposal(str(transparent))
        assert a["diagnostics"]["foreground_source"]=="source_alpha" and np.array_equal(a["_label_map"],b["_label_map"])
        assert validate_partition(a["_masks"],~a["_masks"]["background"])
        opaque=root/"opaque.png"; _anime_image().convert("RGB").save(opaque); result=generate_semantic_region_proposal(str(opaque))
        assert result["diagnostics"]["foreground_source"]=="border_color_separation"
        assert result["coverage"]["foreground_unknown_pixel_count"]>=0
        assert any(record["label"] in {"hair","face_skin","clothing","foreground_unknown"} for record in result["regions"])


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


def test_cli_validation():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); image=root/"source.png"; _anime_image().save(image); geometry=root/"geometry.json"; geometry.write_text(json.dumps(_geometry()),encoding="utf-8")
        args=SimpleNamespace(case=None,image=str(image),geometry=str(geometry),plan=None,visible_contribution_report=None,output_dir=str(root/"out"),backend="heuristic-anime",region_hints=None,
            foreground_alpha_threshold=8,color_clusters=8,minimum_region_area=4,unknown_warning_threshold=.9,attribution_overlap_threshold=.05,ambiguity_margin=.08,visibility_resolution_scale=1.0,
            debug_shape_indexes=None,overwrite=False,skip_layer_attribution=False,no_visualizations=True)
        result=run_from_args(args); validate_outputs(_public_regions(result["regions"]),result["attribution"],_geometry())


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
