import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from engine.analyzer.layer_region_attribution import attribute_layers_to_semantic_regions
from engine.analyzer.shape_visibility_analyzer import analyze_shape_visibility
from engine.output.semantic_region_writer import write_layer_region_attribution_csv,write_layer_region_attribution_json,write_region_layer_summary,write_semantic_regions_json
from engine.vision.semantic_regions.region_backend import generate_semantic_region_proposal
from engine.vision.semantic_regions.region_visualizer import write_region_visualizations


def main():
    parser=_parser()
    try: result=run_from_args(parser.parse_args())
    except Exception as exc: print(f"Semantic region generation failed: {exc}",file=sys.stderr); return 1
    print(f"Status: {result['regions']['status']}"); print(f"Backend: {result['regions']['backend']}"); print(f"Shapes: {result.get('attribution',{}).get('shape_count','skipped')}"); return 0


def run_from_args(args):
    paths=_paths(args); options={"backend":args.backend,"foreground_alpha_threshold":args.foreground_alpha_threshold,"color_clusters":args.color_clusters,
        "minimum_region_area":args.minimum_region_area,"unknown_warning_threshold":args.unknown_warning_threshold,"region_hints":str(paths["hints"]) if paths["hints"] else None}
    regions=generate_semantic_region_proposal(str(paths["image"]),options); geometry=_load(paths["geometry"]); attribution=None
    if not args.skip_layer_attribution:
        size=regions["image_size"]; visibility=analyze_shape_visibility(geometry,size["width"],size["height"],{"visibility_resolution_scale":args.visibility_resolution_scale})
        attribution=attribute_layers_to_semantic_regions(geometry,regions,visibility,{"visibility_resolution_scale":args.visibility_resolution_scale,
            "attribution_overlap_threshold":args.attribution_overlap_threshold,"ambiguity_margin":args.ambiguity_margin,
            "geometry_path":str(paths["geometry"]),"semantic_regions_path":str(paths["output"]/"semantic_regions.json"),
            "plan":_load_optional(paths["plan"]),"visible_contribution_report":_load_optional(paths["visible"])})
    visual_paths={}; mask_paths={}
    if not args.no_visualizations: visual_paths,mask_paths=write_region_visualizations(regions,paths["output"],attribution,args.overwrite)
    for record in regions["regions"]:
        if record["label"] in mask_paths: record["mask_path"]=mask_paths[record["label"]]
    regions["outputs"]=visual_paths
    outputs=_output_paths(paths["output"]); write_semantic_regions_json(regions,outputs["regions"],args.overwrite)
    _write_json(regions["diagnostics"],outputs["diagnostics"],args.overwrite)
    if attribution:
        write_layer_region_attribution_json(attribution,outputs["attribution"],args.overwrite); write_layer_region_attribution_csv(attribution,outputs["csv"],args.overwrite)
        write_region_layer_summary(attribution["region_summaries"],outputs["summary_json"],args.overwrite); _write_summary(attribution,outputs["summary_txt"],args.overwrite)
    return {"regions":regions,"attribution":attribution,"outputs":outputs,"visual_paths":visual_paths}


def _parser():
    p=argparse.ArgumentParser(description="Generate conservative semantic region proposals and layer attribution.")
    p.add_argument("--case"); p.add_argument("--image"); p.add_argument("--geometry"); p.add_argument("--plan"); p.add_argument("--visible-contribution-report"); p.add_argument("--output-dir")
    p.add_argument("--backend",choices=["auto","heuristic-anime"],default="auto"); p.add_argument("--region-hints")
    p.add_argument("--foreground-alpha-threshold",type=int,default=8); p.add_argument("--color-clusters",type=int,default=12); p.add_argument("--minimum-region-area",type=int,default=12)
    p.add_argument("--unknown-warning-threshold",type=float,default=.65); p.add_argument("--attribution-overlap-threshold",type=float,default=.12); p.add_argument("--ambiguity-margin",type=float,default=.08)
    p.add_argument("--visibility-resolution-scale",type=float,default=1.0); p.add_argument("--debug-shape-indexes"); p.add_argument("--overwrite",action="store_true"); p.add_argument("--skip-layer-attribution",action="store_true"); p.add_argument("--no-visualizations",action="store_true"); return p


def _paths(args):
    case=Path(args.case) if args.case else None
    def choose(value,relative,optional=False):
        path=Path(value) if value else (case/relative if case else None)
        return path if path and (path.exists() or not optional) else None
    image=choose(args.image,"source_full.png"); geometry=choose(args.geometry,"paintstudio_geometry.json")
    if not image or not geometry: raise ValueError("Provide --case or both --image and --geometry.")
    return {"image":image,"geometry":geometry,"plan":choose(args.plan,"optimization_plan.json",True),"visible":choose(args.visible_contribution_report,"visible_contribution/visible_contribution_report.json",True),
        "hints":choose(args.region_hints,"semantic_region_hints.json",True),"output":Path(args.output_dir) if args.output_dir else (case/"semantic_regions" if case else Path("output/semantic_regions"))}


def _output_paths(root): return {"regions":str(root/"semantic_regions.json"),"diagnostics":str(root/"semantic_region_diagnostics.json"),"attribution":str(root/"layer_region_attribution.json"),"csv":str(root/"layer_region_attribution.csv"),"summary_json":str(root/"region_layer_summary.json"),"summary_txt":str(root/"region_layer_summary.txt")}
def _write_summary(attribution,path,overwrite):
    lines=["FLO Region Layer Summary","ANALYSIS ONLY","",f"Shapes: {attribution['shape_count']}",f"Attributed: {attribution['attributed_shape_count']}",f"Fully occluded: {attribution['fully_occluded_shape_count']}",f"Ambiguous: {attribution['ambiguous_shape_count']}",f"Sensitive: {attribution['sensitive_shape_count']}",""]
    for label,item in attribution["region_summaries"].items(): lines.append(f"{label}: primary={item['primary_attributed_shape_count']} all={item['attributed_shape_count']}")
    _write_text(path,"\n".join(lines),overwrite)
def _write_json(data,path,overwrite):
    output=Path(path); output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists() and not overwrite: raise FileExistsError(output)
    output.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
def _write_text(path,text,overwrite):
    output=Path(path)
    if output.exists() and not overwrite: raise FileExistsError(output)
    output.write_text(text,encoding="utf-8")
def _load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def _load_optional(path): return _load(path) if path else None
if __name__=="__main__": raise SystemExit(main())
