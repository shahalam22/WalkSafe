import math
from collections import deque

import numpy as np

from walksafe.config import CFG, AgentConfig
from walksafe.perception import Box

CLS_NAME = {
    0:"person", 1:"bicycle", 2:"car", 3:"motorcycle", 5:"bus",
    6:"train", 7:"truck", 9:"traffic_light", 10:"fire_hydrant",
    11:"stop_sign", 16:"dog", 17:"horse", 56:"chair", 57:"couch",
}
for i in range(80):
    CLS_NAME.setdefault(i, f"obj{i}")


def classify_motion(tid, cx, cy, fi, depth_m, track_history, cfg: AgentConfig = CFG.agents):
    if tid not in track_history:
        track_history[tid] = deque(maxlen=cfg.motion_window)
    track_history[tid].append((cx, cy, fi, depth_m))
    hist = track_history[tid]

    if len(hist) < 4:
        return "new"

    x0, y0, _, d0 = hist[0]
    xn, yn, _, dn = hist[-1]
    dx = xn - x0;  dy = yn - y0
    dist_px = (dx**2 + dy**2)**0.5
    if dist_px < 5:
        return "static"

    depth_delta = (dn - d0) if (d0 > 0 and dn > 0) else 0
    lateral_dom = abs(dx) > abs(dy) * 1.2
    depth_dom   = abs(depth_delta) > 0.3 and not lateral_dom

    if len(hist) >= 6:
        angles = []
        for i in range(1, len(hist)):
            px2, py2 = hist[i-1][0], hist[i-1][1]
            cx2, cy2 = hist[i][0],   hist[i][1]
            if (cx2-px2)**2 + (cy2-py2)**2 > 4:
                angles.append(math.degrees(math.atan2(cy2-py2, cx2-px2)))
        if len(angles) >= 4 and float(np.std(np.diff(angles))) > 60:
            return "erratic"

    rs  = ((hist[-1][0]-hist[-2][0])**2 + (hist[-1][1]-hist[-2][1])**2)**0.5
    es  = ((hist[-3][0]-hist[-4][0])**2 + (hist[-3][1]-hist[-4][1])**2)**0.5
    if rs < 3 and es > 8:  return "stopping"
    if rs > 8 and es < 3:  return "starting"
    if lateral_dom:
        return "crossing-R" if dx > 0 else "crossing-L"
    if depth_dom:
        if depth_delta < 0:
            return "parallel_counter" if abs(dx) < 15 else "approaching"
        else:
            return "parallel_same" if abs(dx) < 15 else "receding"
    if dy > 8:    return "approaching"
    elif dy < -8: return "receding"
    return "static"


def risk_level(motion, dist_m, ttc_s, cfg: AgentConfig = CFG.agents):
    if ttc_s is not None and ttc_s < cfg.ttc_emergency:  return "critical"
    if dist_m > 0 and dist_m < 1.0 and motion in ("approaching","parallel_counter"):
        return "critical"
    if ttc_s is not None and ttc_s < cfg.ttc_critical:   return "high"
    if ttc_s is not None and ttc_s < cfg.ttc_urgent:     return "moderate"
    if motion == "erratic":                              return "moderate"
    return "low"


def measure(boxes: list[Box], depth_arr, frame_idx, track_history, cfg: AgentConfig = CFG.agents):
    """Distance, motion, approach speed, TTC and risk for each detected box."""
    H    = depth_arr.shape[0]
    dets = []

    for b in boxes:
        x1, y1, x2, y2, tid = b.x1, b.y1, b.x2, b.y2, b.tid
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        fy1   = y1 + int((y2 - y1) * 0.6)
        patch = depth_arr[max(fy1,0):y2, max(x1,0):x2]
        if patch.size > 0:
            dist_m       = round(float(np.percentile(patch, 10)), 2)
            dist_m_sigma = round(float(np.std(patch)), 3)
        else:
            dist_m       = round(max(0.3, min(6.0, (1.0 - y2/H) * 9.0)), 2)
            dist_m_sigma = -1.0

        motion = classify_motion(tid, cx, cy, frame_idx, dist_m, track_history, cfg) \
                 if tid >= 0 else "static"

        hist = track_history.get(tid, [])
        if len(hist) >= 4:
            d0 = hist[0][3];  dn = hist[-1][3]
            dt = len(hist) / 30.0
            approach_speed = round((d0-dn)/(dt+1e-8), 3) \
                             if (d0 > 0 and dn > 0) else 0.0
        else:
            approach_speed = 0.0

        ttc = round(dist_m / (approach_speed + 1e-8), 2) \
              if approach_speed > 0.1 and dist_m > 0 else None
        if ttc: ttc = min(ttc, 99.0)

        dets.append({
            "cls": b.cls, "name": CLS_NAME.get(b.cls, "?"),
            "conf": round(b.conf, 2), "box": [x1, y1, x2, y2],
            "tid": tid, "motion": motion,
            "cx": cx, "cy": cy,
            "dist_m": dist_m, "dist_m_sigma": dist_m_sigma,
            "approach_speed_ms": approach_speed,
            "ttc_s": ttc, "risk_level": risk_level(motion, dist_m, ttc, cfg),
            "track_age": len(hist),
        })

    return dets
