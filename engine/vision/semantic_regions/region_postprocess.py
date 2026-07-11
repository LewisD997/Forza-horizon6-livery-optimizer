import numpy as np

from .region_schema import EXCLUSIVE_LABELS, REGION_IDS, make_region_record


PRIORITY = ("eyes", "mouth", "face_skin", "body_skin", "hair", "clothing", "foreground_unknown", "background")


def connected_components(mask):
    mask = np.asarray(mask, dtype=bool); seen = np.zeros(mask.shape, dtype=bool); components = []
    height, width = mask.shape
    for y, x in zip(*np.where(mask & ~seen)):
        stack = [(int(y), int(x))]; seen[y, x] = True; points = []
        while stack:
            cy, cx = stack.pop(); points.append((cy, cx))
            for ny, nx in ((cy-1,cx),(cy+1,cx),(cy,cx-1),(cy,cx+1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny,nx] and not seen[ny,nx]:
                    seen[ny,nx] = True; stack.append((ny,nx))
        components.append(points)
    return components


def filter_components(mask, minimum_area=8, keep_largest=True):
    components = connected_components(mask); out = np.zeros_like(mask, dtype=bool)
    if not components: return out
    largest = max(len(component) for component in components)
    for component in components:
        if len(component) >= minimum_area or (keep_largest and len(component) == largest):
            ys, xs = zip(*component); out[np.array(ys), np.array(xs)] = True
    return out


def fill_small_holes(mask, maximum_area=16, domain_mask=None):
    inverse = ~np.asarray(mask, dtype=bool); out = np.array(mask, dtype=bool, copy=True)
    h, w = out.shape
    for component in connected_components(inverse):
        touches = any(y in {0,h-1} or x in {0,w-1} for y,x in component)
        if not touches and len(component) <= maximum_area:
            ys, xs = zip(*component); out[np.array(ys), np.array(xs)] = True
    if domain_mask is not None:
        out &= np.asarray(domain_mask, dtype=bool)
    return out


def resolve_exclusive_masks(masks, foreground):
    foreground = np.asarray(foreground, dtype=bool); assigned = np.zeros(foreground.shape, dtype=bool); result = {}
    for label in PRIORITY[:-2]:
        candidate = np.asarray(masks.get(label, np.zeros_like(foreground)), dtype=bool) & foreground & ~assigned
        result[label] = candidate; assigned |= candidate
    result["foreground_unknown"] = foreground & ~assigned
    result["background"] = ~foreground
    for label in result:
        if label != "background":
            result[label] &= foreground
    return result


def build_label_map(masks):
    shape = next(iter(masks.values())).shape; label_map = np.full(shape, REGION_IDS["unknown"], dtype=np.uint8)
    for label in EXCLUSIVE_LABELS: label_map[masks.get(label, False)] = REGION_IDS[label]
    label_map[masks["background"]] = REGION_IDS["background"]
    return label_map


def bbox_for_mask(mask):
    ys, xs = np.where(mask)
    if len(xs) == 0: return {"x": 0, "y": 0, "width": 0, "height": 0}
    x0,y0,x1,y1 = int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
    return {"x": x0, "y": y0, "width": x1-x0, "height": y1-y0}


def region_records(masks, confidences, foreground_count, backend):
    records = []
    for label in EXCLUSIVE_LABELS:
        mask = masks.get(label); area = int(mask.sum()) if mask is not None else 0
        if area:
            records.append(make_region_record(label, confidences.get(label, 0.35), bbox_for_mask(mask), area, foreground_count, backend,
                evidence=["heuristic_color_spatial_component_proposal"]))
    return records


def validate_partition(masks, foreground):
    total = np.zeros(foreground.shape, dtype=np.uint8)
    for label in EXCLUSIVE_LABELS: total += np.asarray(masks.get(label, False), dtype=np.uint8)
    return bool(np.all(total == 1) and np.all(masks["background"] == ~foreground))
