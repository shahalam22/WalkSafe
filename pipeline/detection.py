import cv2
import numpy as np
import math
from collections import deque
import models
from config import CFG

# ── Class names ───────────────────────────────────────────────────────────────
CLS_NAME = {
    0:"person", 1:"bicycle", 2:"car", 3:"motorcycle", 5:"bus",
    6:"train", 7:"truck", 9:"traffic_light", 10:"fire_hydrant",
    11:"stop_sign", 16:"dog", 17:"horse", 56:"chair", 57:"couch",
}
for i in range(80):
    CLS_NAME.setdefault(i, f"obj{i}")

# ── Colours ───────────────────────────────────────────────────────────────────
def _cls_color(c):
    if c == 0:             return (0, 220, 80)
    if c in [1, 3]:        return (255, 165, 0)
    if c == 2:             return (0, 180, 255)
    if c in [5, 6]:        return (160, 0, 255)
    if c == 7:             return (255, 0, 120)
    if c in range(14, 24): return (0, 200, 255)
    return (160, 160, 160)

CLS_COLOR    = {i: _cls_color(i) for i in range(80)}

MOTION_COLOR = {
    "static":           (160,160,160), "approaching":      (0,50,230),
    "parallel_counter": (0,0,200),     "receding":         (0,200,80),
    "parallel_same":    (0,160,60),    "crossing-R":       (0,140,255),
    "crossing-L":       (0,100,200),   "stopping":         (0,80,180),
    "starting":         (100,200,255), "erratic":          (0,0,150),
    "new":              (200,200,200),
}

RISK_COLOR = {
    "critical": (0,0,220), "high":     (0,100,255),
    "moderate": (0,200,255),"low":     (80,180,80),
}


def classify_motion(tid, cx, cy, fi, depth_m, track_history):
    if tid not in track_history:
        track_history[tid] = deque(maxlen=CFG["motion_window"])
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


def risk_level(motion, dist_m, ttc_s):
    if ttc_s is not None and ttc_s < CFG["ttc_emergency"]:  return "critical"
    if dist_m > 0 and dist_m < 1.0 and motion in ("approaching","parallel_counter"):
        return "critical"
    if ttc_s is not None and ttc_s < CFG["ttc_critical"]:   return "high"
    if ttc_s is not None and ttc_s < CFG["ttc_urgent"]:     return "moderate"
    if motion == "erratic":                                   return "moderate"
    return "low"


def run(frame_bgr, depth_arr, frame_idx, track_history):
    H, W = frame_bgr.shape[:2]
    try:
        results = models.yolo_model.track(
            frame_bgr, conf=CFG["yolo_conf"],
            verbose=False, persist=True, tracker="bytetrack.yaml")[0]
    except Exception:
        results = models.yolo_model.predict(
            frame_bgr, conf=CFG["yolo_conf"], verbose=False)[0]

    ann  = frame_bgr.copy()
    dets = []

    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        cls = int(box.cls[0])
        cf  = float(box.conf[0])
        cx  = (x1 + x2) // 2
        cy  = (y1 + y2) // 2
        tid = int(box.id[0]) if box.id is not None else -1

        fy1   = y1 + int((y2 - y1) * 0.6)
        patch = depth_arr[max(fy1,0):y2, max(x1,0):x2]
        if patch.size > 0:
            dist_m       = round(float(np.percentile(patch, 10)), 2)
            dist_m_sigma = round(float(np.std(patch)), 3)
        else:
            dist_m       = round(max(0.3, min(6.0, (1.0 - y2/H) * 9.0)), 2)
            dist_m_sigma = -1.0

        motion = classify_motion(tid, cx, cy, frame_idx, dist_m, track_history) \
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

        risk = risk_level(motion, dist_m, ttc)
        col  = CLS_COLOR.get(cls, (180,180,180))
        mc   = MOTION_COLOR.get(motion, (180,180,180))
        th   = 3 if risk == "critical" else 2 if risk == "high" else 1

        cv2.rectangle(ann, (x1,y1), (x2,y2), col, th)
        lbl = (f"#{tid} {CLS_NAME.get(cls,'?')} [{motion}] {dist_m}m"
               if tid >= 0 else
               f"{CLS_NAME.get(cls,'?')} [{motion}] {dist_m}m")
        (tw, fh), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
        cv2.rectangle(ann, (x1, y1-fh-5), (x1+tw+4, y1), col, -1)
        cv2.putText(ann, lbl, (x1+2, y1-3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0,0,0), 1)

        if len(hist) >= 4:
            x0p, y0p = hist[-4][0], hist[-4][1]
            ax = max(0, min(W-1, cx + int((cx-x0p)*3)))
            ay = max(0, min(H-1, cy + int((cy-y0p)*3)))
            if (ax, ay) != (cx, cy):
                cv2.arrowedLine(ann, (cx,cy), (ax,ay), mc, 2, tipLength=0.4)

        cv2.circle(ann, (x2-6, y1+6), 5, RISK_COLOR.get(risk,(120,120,120)), -1)

        dets.append({
            "cls": cls, "name": CLS_NAME.get(cls,"?"),
            "conf": round(cf,2), "box": [x1,y1,x2,y2],
            "tid": tid, "motion": motion,
            "cx": cx, "cy": cy,
            "dist_m": dist_m, "dist_m_sigma": dist_m_sigma,
            "approach_speed_ms": approach_speed,
            "ttc_s": ttc, "risk_level": risk,
            "track_age": len(hist),
        })

    return ann, dets