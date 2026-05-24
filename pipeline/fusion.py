import cv2
import numpy as np
import math
from pipeline.depth import colormap as depth_colormap
from pipeline.suggestion import SUGGESTION_COLOR
from config import CFG

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


def build_panel(frame_bgr, depth_arr, flow_bgr, det_frame, gaps, ego, H, W):
    depth_col = depth_colormap(depth_arr)
    fused     = cv2.addWeighted(frame_bgr, 0.60, depth_col, 0.25, 0)
    fused     = cv2.addWeighted(fused,     0.85, flow_bgr,  0.15, 0)
    fused     = cv2.addWeighted(fused,     0.75, det_frame, 0.25, 0)

    surface_y = int(H * CFG["zone_surface_top_frac"])

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


def build_advisory(dets, gaps, ego, command, detail):
    """
    Receives pre-computed suggestion (command, detail) from ui.py.
    Purely renders — no decision logic here.

    4 rows:
      Row 1 — suggested action command
      Row 2 — person's actual action (logged + displayed)
      Row 3 — best gap
      Row 4 — most critical agent
    """
    W   = 518    # will be overridden by caller passing W
    ah  = 170
    # W is passed in — see signature update below
    ...


def build_advisory(dets, gaps, ego, command, detail, W):
    ah   = 170
    adv  = np.zeros((ah, W, 3), dtype=np.uint8)
    adv[:] = (18, 18, 18)
    font = cv2.FONT_HERSHEY_SIMPLEX
    lh   = ah // 5

    sug_col = SUGGESTION_COLOR.get(command, (200,200,200))

    # ── Row 1: Suggested command ──────────────────────────────────────
    cv2.rectangle(adv, (0,0), (W, lh+8), (28,28,28), -1)
    cv2.putText(adv,
                f"  ► {command.replace('_',' ').upper()}   {detail}",
                (6, lh), font, 0.60, sug_col, 2)
    cv2.line(adv, (0, lh+8), (W, lh+8), sug_col, 2)

    # ── Row 2: Person's actual action ────────────────────────────────
    ego_col = ACTION_COLOR.get(ego["action"], (200,200,200))
    cv2.putText(adv,
                f"  YOU: {ego['action'].replace('_',' ')}  "
                f"|  {ego['ego_speed_ms']:.2f} m/s",
                (6, lh*2+4), font, 0.44, ego_col, 1)

    # ── Row 3: Best gap ───────────────────────────────────────────────
    if gaps:
        best    = max(gaps, key=lambda g: g["width_px"])
        gap_col = (0,220,80)  if best["width_m"] >= CFG["gap_comfortable"] else \
                  (0,200,200) if best["width_m"] >= CFG["gap_tight"]       else \
                  (0,120,255)
        cv2.putText(adv,
                    f"  GAP: {best['width_m']:.1f}m wide  "
                    f"|  {best['dist_m']:.1f}m away  "
                    f"|  {best['direction'].upper()}",
                    (6, lh*3+4), font, 0.44, gap_col, 1)
    else:
        cv2.putText(adv, "  GAP: none detected",
                    (6, lh*3+4), font, 0.44, (0,60,220), 1)

    # ── Row 4: Most critical agent ────────────────────────────────────
    RISK_ORDER  = {"critical":0,"high":1,"moderate":2,"low":3}
    sorted_dets = sorted(dets,
                         key=lambda d:(RISK_ORDER.get(d["risk_level"],3), d["dist_m"]))
    RCOL = {"critical":(0,0,220),"high":(0,100,255),
            "moderate":(0,200,255),"low":(80,180,80)}
    if sorted_dets:
        a       = sorted_dets[0]
        ttc_str = f" TTC {a['ttc_s']:.1f}s" \
                  if a.get("ttc_s") and a["ttc_s"] < 10 else ""
        cv2.putText(adv,
                    f"  AGENT [{a['risk_level'].upper()}]: "
                    f"{a['name']} {a['motion'].replace('-',' ')} "
                    f"at {a['dist_m']:.1f}m{ttc_str}",
                    (6, lh*4+4), font, 0.44,
                    RCOL.get(a["risk_level"],(180,180,180)), 1)
    else:
        cv2.putText(adv, "  AGENT: none",
                    (6, lh*4+4), font, 0.44, (80,180,80), 1)

    cv2.line(adv, (0,0), (W,0), (60,60,60), 2)
    return adv