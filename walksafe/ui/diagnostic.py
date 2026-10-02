"""Fusion panel for sighted reviewers: camera, depth, flow, agents and the decision."""
import math

import cv2
import numpy as np

from walksafe.config import CFG, Config

CLS_COLOR = {}
for _c in range(80):
    if _c == 0:               CLS_COLOR[_c] = (0, 220, 80)
    elif _c in (1, 3):        CLS_COLOR[_c] = (255, 165, 0)
    elif _c == 2:             CLS_COLOR[_c] = (0, 180, 255)
    elif _c in (5, 6):        CLS_COLOR[_c] = (160, 0, 255)
    elif _c == 7:             CLS_COLOR[_c] = (255, 0, 120)
    elif _c in range(14, 24): CLS_COLOR[_c] = (0, 200, 255)
    else:                     CLS_COLOR[_c] = (160, 160, 160)

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

COMMAND_COLOR = {
    "stop":              (0,   0,   220),
    "yield":             (0,   180, 255),
    "slow_down":         (0,   100, 255),
    "walk_forward":      (0,   200,  80),
    "walk_forward_slow": (0,   180, 160),
    "step_left":         (255, 160,   0),
    "step_right":        (255, 120,   0),
    "turn_left":         (200,  80, 255),
    "turn_right":        (140,  60, 255),
}

ACTION_COLOR = {
    "walking_fast":      (0,   200,  80),
    "walking_forward":   (0,   180,  60),
    "walking_slow":      (0,   160,  50),
    "walking_very_slow": (0,   140,  40),
    "standing_still":    (120, 120, 120),
    "stopping":          (180, 180,  40),
    "stepping_left":     (255, 160,   0),
    "stepping_right":    (255, 120,   0),
    "turning_left":      (255,  60,  60),
    "turning_right":     (200,  40,  40),
}


def render(r, track_history, cfg: Config = CFG):
    """FrameResult -> RGB image of the fusion panel stacked on the advisory strip."""
    H, W      = r.frame_bgr.shape[:2]
    det_frame = draw_agents(r.frame_bgr, r.dets, track_history)
    flow_bgr  = flow_to_bgr(r.flow, r.frame_bgr, cfg) if r.flow is not None \
                else np.zeros_like(r.frame_bgr)
    panel = build_panel(r.frame_bgr, r.depth_arr, flow_bgr, det_frame, r.gaps, H, W, cfg)
    strip = build_advisory(r.dets, r.gaps, r.ego, r.command, r.detail, W, cfg)
    return cv2.cvtColor(np.vstack([panel, strip]), cv2.COLOR_BGR2RGB)


def depth_colormap(depth_arr, cfg: Config = CFG):
    lo  = np.percentile(depth_arr, cfg.ui.depth_pct_low)
    hi  = np.percentile(depth_arr, cfg.ui.depth_pct_high)
    clp = np.clip(depth_arr, lo, hi)
    n   = ((clp - lo) / (hi - lo + 1e-8) * 255).astype(np.uint8)
    return cv2.applyColorMap(n, cv2.COLORMAP_VIRIDIS)


def flow_to_bgr(flow, frame_bgr, cfg: Config = CFG):
    H, W   = flow.shape[:2]
    fx, fy = flow[..., 0], flow[..., 1]

    angle    = (np.arctan2(fy, fx) + np.pi) / (2 * np.pi)
    mag      = np.sqrt(fx**2 + fy**2)
    mag_norm = np.clip(mag / (np.percentile(mag, 99) + 1e-6), 0, 1)

    hsv         = np.zeros((H, W, 3), dtype=np.uint8)
    hsv[..., 0] = (angle * 179).astype(np.uint8)
    hsv[..., 1] = 220
    hsv[..., 2] = (mag_norm * 255).astype(np.uint8)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    bgr = cv2.addWeighted(frame_bgr, 0.25, bgr, 0.75, 0)

    step  = cfg.ui.flow_arrow_step
    scale = 3.0
    for y in range(step // 2, H, step):
        for x in range(step // 2, W, step):
            dx, dy = float(fx[y, x]), float(fy[y, x])
            if math.sqrt(dx*dx + dy*dy) < 0.5:
                continue
            x2 = max(0, min(W-1, int(x + dx*scale)))
            y2 = max(0, min(H-1, int(y + dy*scale)))
            hue_local = int((math.atan2(dy, dx) + math.pi) / (2*math.pi) * 179)
            arrow_bgr = cv2.cvtColor(
                np.uint8([[[hue_local, 220, 230]]]),
                cv2.COLOR_HSV2BGR)[0][0].tolist()
            cv2.arrowedLine(bgr, (x, y), (x2, y2), arrow_bgr, 1, tipLength=0.35)
    return bgr


def draw_agents(frame_bgr, dets, track_history):
    H, W = frame_bgr.shape[:2]
    ann  = frame_bgr.copy()
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        tid, cx, cy    = d["tid"], d["cx"], d["cy"]
        risk, motion   = d["risk_level"], d["motion"]
        col  = CLS_COLOR.get(d["cls"], (180,180,180))
        mc   = MOTION_COLOR.get(motion, (180,180,180))
        th   = 3 if risk == "critical" else 2 if risk == "high" else 1

        cv2.rectangle(ann, (x1,y1), (x2,y2), col, th)
        lbl = (f"#{tid} {d['name']} [{motion}] {d['dist_m']}m"
               if tid >= 0 else
               f"{d['name']} [{motion}] {d['dist_m']}m")
        (tw, fh), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
        cv2.rectangle(ann, (x1, y1-fh-5), (x1+tw+4, y1), col, -1)
        cv2.putText(ann, lbl, (x1+2, y1-3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0,0,0), 1)

        hist = track_history.get(tid, [])
        if len(hist) >= 4:
            x0p, y0p = hist[-4][0], hist[-4][1]
            ax = max(0, min(W-1, cx + int((cx-x0p)*3)))
            ay = max(0, min(H-1, cy + int((cy-y0p)*3)))
            if (ax, ay) != (cx, cy):
                cv2.arrowedLine(ann, (cx,cy), (ax,ay), mc, 2, tipLength=0.4)

        cv2.circle(ann, (x2-6, y1+6), 5, RISK_COLOR.get(risk,(120,120,120)), -1)
    return ann


def build_panel(frame_bgr, depth_arr, flow_bgr, det_frame, gaps, H, W, cfg: Config = CFG):
    depth_col = depth_colormap(depth_arr, cfg)
    fused     = cv2.addWeighted(frame_bgr, 0.60, depth_col, 0.25, 0)
    fused     = cv2.addWeighted(fused,     0.85, flow_bgr,  0.15, 0)
    fused     = cv2.addWeighted(fused,     0.75, det_frame, 0.25, 0)

    surface_y = int(H * cfg.openings.surface_top_frac)

    for g in gaps:
        cx_g, hw = g["cx_px"], g["width_px"] // 2
        x1, x2   = max(0, cx_g-hw), min(W, cx_g+hw)
        overlay  = fused.copy()
        overlay[surface_y:, x1:x2] = (0, 180, 0)
        fused = cv2.addWeighted(fused, 0.6, overlay, 0.4, 0)
        cv2.putText(fused, f"GAP {g['dist_m']:.1f}m",
                    (max(x1+4, cx_g-25), surface_y+22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,80), 2)
        cv2.arrowedLine(fused, (W//2, H-10), (cx_g, surface_y+30),
                        (0,255,80), 2, tipLength=0.15)

    for frac, label in [(0.18,"FREE"),(0.38,"OVERHEAD"),(0.62,"TORSO")]:
        y = int(H * frac)
        cv2.line(fused, (0,y), (W,y), (200,200,200), 1)
        cv2.putText(fused, label, (4,y-4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, (200,200,200), 1)

    return fused


def build_advisory(dets, gaps, ego, command, detail, W, cfg: Config = CFG):
    ah   = 170
    adv  = np.zeros((ah, W, 3), dtype=np.uint8)
    adv[:] = (18, 18, 18)
    font = cv2.FONT_HERSHEY_SIMPLEX
    lh   = ah // 5

    sug_col = COMMAND_COLOR.get(command, (200,200,200))

    # Row 1: the command
    cv2.rectangle(adv, (0,0), (W, lh+8), (28,28,28), -1)
    cv2.putText(adv,
                f"  ► {command.replace('_',' ').upper()}   {detail}",
                (6, lh), font, 0.60, sug_col, 2)
    cv2.line(adv, (0, lh+8), (W, lh+8), sug_col, 2)

    # Row 2: what the user is doing
    ego_col = ACTION_COLOR.get(ego["action"], (200,200,200))
    cv2.putText(adv,
                f"  YOU: {ego['action'].replace('_',' ')}  "
                f"|  {ego['ego_speed_ms']:.2f} m/s",
                (6, lh*2+4), font, 0.44, ego_col, 1)

    # Row 3: best gap
    if gaps:
        best    = max(gaps, key=lambda g: g["width_px"])
        gap_col = (0,220,80)  if best["width_m"] >= cfg.openings.comfortable_m else \
                  (0,200,200) if best["width_m"] >= cfg.openings.tight_m       else \
                  (0,120,255)
        cv2.putText(adv,
                    f"  GAP: {best['width_m']:.1f}m wide  "
                    f"|  {best['dist_m']:.1f}m away  "
                    f"|  {best['direction'].upper()}",
                    (6, lh*3+4), font, 0.44, gap_col, 1)
    else:
        cv2.putText(adv, "  GAP: none detected",
                    (6, lh*3+4), font, 0.44, (0,60,220), 1)

    # Row 4: most critical agent
    risk_order  = {"critical":0,"high":1,"moderate":2,"low":3}
    sorted_dets = sorted(dets,
                         key=lambda d:(risk_order.get(d["risk_level"],3), d["dist_m"]))
    if sorted_dets:
        a       = sorted_dets[0]
        ttc_str = f" TTC {a['ttc_s']:.1f}s" \
                  if a.get("ttc_s") and a["ttc_s"] < 10 else ""
        cv2.putText(adv,
                    f"  AGENT [{a['risk_level'].upper()}]: "
                    f"{a['name']} {a['motion'].replace('-',' ')} "
                    f"at {a['dist_m']:.1f}m{ttc_str}",
                    (6, lh*4+4), font, 0.44,
                    RISK_COLOR.get(a["risk_level"],(180,180,180)), 1)
    else:
        cv2.putText(adv, "  AGENT: none",
                    (6, lh*4+4), font, 0.44, (80,180,80), 1)

    cv2.line(adv, (0,0), (W,0), (60,60,60), 2)
    return adv
