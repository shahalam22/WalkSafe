import cv2
import numpy as np
import math
from pipeline.depth import colormap as depth_colormap
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

# Suggestion commands mirror the action taxonomy
SUGGESTION_COLOR = {
    "stop":             (0,   0,   220),
    "slow_down":        (0,   100, 255),
    "walk_forward":     (0,   200,  80),
    "walk_forward_slow":(0,   180, 160),
    "step_left":        (255, 160,   0),
    "step_right":       (255, 120,   0),
    "turn_left":        (200,  80, 255),
    "turn_right":       (140,  60, 255),
    "yield":            (0,   180, 255),
}

# ══════════════════════════════════════════════════════════════════
# NAVIGATION SUGGESTION ENGINE
# Input:  gaps, agents (depth + motion + risk)
# Output: action command for the person to take
# ══════════════════════════════════════════════════════════════════

def generate_suggestion(ego, dets, gap_list):
    """
    Pure scene reasoning — ego action is NOT used here.
    Returns:
        command   — action to take  e.g. "step_right", "walk_forward"
        detail    — short context   e.g. "1.4m gap at 2.1m"
        reasoning — structured str  for DB storage later
    """
    RISK_ORDER  = {"critical":0, "high":1, "moderate":2, "low":3}
    top_agents  = sorted(dets,
                         key=lambda d: (RISK_ORDER.get(d["risk_level"],3), d["dist_m"]))
    critical    = [a for a in top_agents if a["risk_level"] == "critical"]
    approaching = [a for a in top_agents
                   if a["motion"] in ("approaching", "parallel_counter", "erratic")]
    crossing    = [a for a in top_agents if "crossing" in a["motion"]]
    best_gap    = max(gap_list, key=lambda g: g["width_px"]) if gap_list else None

    # ── Rule 1: Critical agent — stop immediately ─────────────────────
    if critical:
        a   = critical[0]
        ttc = f"{a['ttc_s']:.1f}s" if a.get("ttc_s") and a["ttc_s"] < 10 else ""
        return (
            "stop",
            f"{a['name']} {a['motion'].replace('-',' ')} {a['dist_m']:.1f}m"
            + (f" TTC {ttc}" if ttc else ""),
            f"critical:{a['name']}:{a['motion']}:{a['dist_m']}m"
        )

    # ── Rule 2: No gap at all ─────────────────────────────────────────
    if not gap_list:
        return (
            "stop",
            "no clear corridor ahead",
            "no_gap"
        )

    # ── Rule 3: Crossing agent with very short TTC — yield ───────────
    if crossing:
        a   = crossing[0]
        ttc = a.get("ttc_s")
        if ttc and ttc < 3.0:
            return (
                "yield",
                f"{a['name']} crossing in {ttc:.1f}s",
                f"crossing:{a['name']}:{ttc:.1f}s"
            )

    # ── Rule 4: Approaching agent — slow or yield ─────────────────────
    if approaching:
        a   = approaching[0]
        ttc = a.get("ttc_s")
        if ttc and ttc < CFG["ttc_critical"]:
            return (
                "stop",
                f"{a['name']} approaching {a['dist_m']:.1f}m TTC {ttc:.1f}s",
                f"approaching_critical:{a['name']}:{a['dist_m']}m"
            )
        if ttc and ttc < CFG["ttc_urgent"]:
            return (
                "yield",
                f"{a['name']} approaching {a['dist_m']:.1f}m",
                f"approaching_urgent:{a['name']}:{a['dist_m']}m"
            )
        if a["dist_m"] < CFG["close_distance_m"]:
            return (
                "slow_down",
                f"{a['name']} ahead {a['dist_m']:.1f}m",
                f"approaching_close:{a['name']}:{a['dist_m']}m"
            )

    # ── Rule 5: Route toward best gap ────────────────────────────────
    dir_    = best_gap["direction"]
    width_m = best_gap["width_m"]
    dist_m  = best_gap["dist_m"]
    detail  = f"{width_m:.1f}m gap {dist_m:.1f}m away"

    # Tight gap — slow approach regardless of direction
    if width_m < CFG["gap_tight"]:
        if dir_ == "ahead":
            return (
                "walk_forward_slow",
                f"tight corridor {detail}",
                f"tight_gap_ahead:{width_m}m:{dist_m}m"
            )
        elif dir_ == "right":
            return (
                "step_right",
                f"tight corridor right — {detail}",
                f"tight_gap_right:{width_m}m:{dist_m}m"
            )
        else:
            return (
                "step_left",
                f"tight corridor left — {detail}",
                f"tight_gap_left:{width_m}m:{dist_m}m"
            )

    # Comfortable gap
    if dir_ == "ahead":
        if width_m >= CFG["gap_comfortable"] and not approaching:
            return (
                "walk_forward",
                detail,
                f"clear_ahead:{width_m}m:{dist_m}m"
            )
        return (
            "walk_forward_slow",
            detail + (" — agent nearby" if approaching else ""),
            f"ahead_with_caution:{width_m}m:{dist_m}m"
        )

    elif dir_ == "right":
        return (
            "step_right",
            detail,
            f"gap_right:{width_m}m:{dist_m}m"
        )

    elif dir_ == "left":
        return (
            "step_left",
            detail,
            f"gap_left:{width_m}m:{dist_m}m"
        )

    # ── Fallback ──────────────────────────────────────────────────────
    return (
        "slow_down",
        "assess surroundings",
        "fallback"
    )


# ══════════════════════════════════════════════════════════════════
# FUSION PANEL
# ══════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════
# ADVISORY STRIP
# ══════════════════════════════════════════════════════════════════

def build_advisory(dets, gaps, ego, depth_arr, W, H):
    """
    4 rows:
      Row 1 — SUGGESTED ACTION  (command from gap+agent reasoning)
      Row 2 — PERSON ACTION     (what they are actually doing — for DB log)
      Row 3 — GAP               (best gap details)
      Row 4 — AGENT             (most critical agent)

    # DB NOTE: persist per frame:
    #   suggestion_command, suggestion_detail, reasoning,
    #   person_action, ego_speed_ms,
    #   gaps, agents, timestamp
    """
    command, detail, reasoning = generate_suggestion(ego, dets, gaps)

    ah   = 170
    adv  = np.zeros((ah, W, 3), dtype=np.uint8)
    adv[:] = (18, 18, 18)
    font = cv2.FONT_HERSHEY_SIMPLEX
    lh   = ah // 5

    sug_col = SUGGESTION_COLOR.get(command, (200,200,200))

    # ── Row 1: Suggested action (large, prominent) ────────────────────
    cv2.rectangle(adv, (0,0), (W, lh+8), (28,28,28), -1)
    cv2.putText(adv,
                f"  ► {command.replace('_',' ').upper()}   {detail}",
                (6, lh), font, 0.60, sug_col, 2)
    cv2.line(adv, (0, lh+8), (W, lh+8), sug_col, 2)

    # ── Row 2: Person's actual action (logged, displayed) ────────────
    ego_col = ACTION_COLOR.get(ego["action"], (200,200,200))
    cv2.putText(adv,
                f"  YOU: {ego['action'].replace('_',' ')}  "
                f"|  {ego['ego_speed_ms']:.2f} m/s",
                (6, lh*2+4), font, 0.44, ego_col, 1)

    # ── Row 3: Gap ────────────────────────────────────────────────────
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
        ttc_str = f" TTC {a['ttc_s']:.1f}s" if a.get("ttc_s") and a["ttc_s"]<10 else ""
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
    return adv, command, detail, reasoning


def _draw_action_banner(frame, ego, H):
    action = ego["action"]
    label  = action.replace("_"," ")
    col    = ACTION_COLOR.get(action, (200,200,200))
    font   = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(label, font, 0.55, 2)
    pad    = 8
    rx1, ry1 = 10, H-th-pad*2-10
    rx2, ry2 = rx1+tw+pad*2, H-10
    cv2.rectangle(frame, (rx1,ry1), (rx2,ry2), col, -1)
    cv2.rectangle(frame, (rx1,ry1), (rx2,ry2), (0,0,0), 1)
    cv2.putText(frame, label, (rx1+pad, ry2-pad), font, 0.55, (0,0,0), 2)
    conf_col = (0,200,0) if ego["action_confidence"]>=0.85 else \
               (0,200,200) if ego["action_confidence"]>=0.60 else (0,0,200)
    cv2.circle(frame, (rx2+10,(ry1+ry2)//2), 6, conf_col, -1)