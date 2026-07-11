import numpy as np

from .region_schema import REGION_IDS


def analyze_semantic_stripes(label_map,domain,width_ratio_threshold=.55):
    foreground_width=max(1,max(int(row.sum()) for row in domain)); affected=[]
    for y in range(1,label_map.shape[0]):
        changed=(label_map[y]!=label_map[y-1])&domain[y]&domain[y-1]
        ratio=float(changed.sum()/foreground_width)
        if ratio>=width_ratio_threshold:
            labels=sorted({int(value) for value in np.unique(np.concatenate((label_map[y-1][changed],label_map[y][changed])))})
            affected.append({"row":y,"transition_pixel_count":int(changed.sum()),"transition_width_ratio":round(ratio,6),"label_ids":labels})
    reverse={value:key for key,value in REGION_IDS.items()}
    ids={item for row in affected for item in row["label_ids"]}
    return {"stripe_diagnostic_version":"0.7.0.2","suspicious_horizontal_transition_count":len(affected),
        "maximum_transition_width_ratio":max((row["transition_width_ratio"] for row in affected),default=0.0),
        "affected_labels":sorted(reverse.get(item,"unknown") for item in ids),"affected_rows":[row["row"] for row in affected],"transitions":affected,
        "spatial_thresholds":[{"name":"head_proximity","usage":"soft_prior"},{"name":"torso_proximity","usage":"soft_prior"}],
        "hard_horizontal_semantic_thresholds":[]}
