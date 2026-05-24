import numpy as np
import math
from config import CFG


def find(depth_arr, H, W):
    surface_y = int(H * CFG["zone_surface_top_frac"])
    strip     = depth_arr[surface_y:, :]
    col_med   = np.median(strip, axis=0)
    norm      = (col_med - col_med.min()) / (col_med.max() - col_med.min() + 1e-8)
    threshold = np.percentile(norm, 55)
    open_mask = (norm >= threshold).astype(np.uint8)

    gaps = []
    in_gap, start = False, 0
    for x, val in enumerate(open_mask):
        if val and not in_gap:
            in_gap, start = True, x
        elif not val and in_gap:
            w = x - start
            if w >= CFG["gap_min_width_px"]:
                gaps.append(_gap_dict(depth_arr, surface_y, H, W, start, x))
            in_gap = False
    if in_gap:
        w = W - start
        if w >= CFG["gap_min_width_px"]:
            gaps.append(_gap_dict(depth_arr, surface_y, H, W, start, W))
    return gaps


def _gap_dict(depth_arr, surface_y, H, W, x1, x2):
    cx_g     = (x1 + x2) // 2
    width_px = x2 - x1
    strip    = depth_arr[surface_y:, x1:x2]
    dist_m   = float(np.median(strip)) if strip.size > 0 else 0.0
    width_m  = round(
        width_px / W * dist_m * 2 * math.tan(math.radians(CFG["fov_deg"] / 2)), 2
    ) if dist_m > 0 else round(width_px / W * 3.0, 2)
    offset   = cx_g - W // 2
    direction = "ahead" if abs(offset) < W*0.15 else ("right" if offset > 0 else "left")
    return {
        "cx_px":     cx_g,
        "width_px":  width_px,
        "width_m":   width_m,
        "dist_m":    round(dist_m, 2),
        "direction": direction,
    }