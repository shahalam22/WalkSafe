"""Fusion panel for sighted reviewers: camera, depth, flow, agents, openings and the decision.

OpenCV's built-in fonts are ASCII only, so every string drawn here must be too.
"""
import math

import cv2
import numpy as np

from walksafe.config import CFG, Config
from walksafe.interpretation.agents import RISKS
from walksafe.interpretation.openings import best_opening

KIND_COLOR = {
    "person": (0, 220, 80), "cyclist": (255, 165, 0), "motorcycle": (255, 165, 0),
    "car": (0, 180, 255), "bus": (160, 0, 255), "truck": (255, 0, 120),
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
    "standing_still":    (120, 120, 120),
    "stopping":          (180, 180,  40),
    "stepping_left":     (255, 160,   0),
    "stepping_right":    (255, 120,   0),
    "turning_left":      (255,  60,  60),
    "turning_right":     (200,  40,  40),
}

FONT = cv2.FONT_HERSHEY_SIMPLEX


def render(r, cfg: Config = CFG):
    """pipeline.FrameResult -> RGB image of the fusion panel stacked on the advisory strip."""
    if r.depth_arr is None:
        panel = r.frame_bgr.copy()
        cv2.putText(panel, f"FRAME REJECTED: {r.quality.cause}", (10, 30), FONT, 0.8, (0, 0, 255), 2)
    else:
        panel = build_panel(r, cfg)
    strip = build_advisory(r, cfg)
    return cv2.cvtColor(np.vstack([panel, strip]), cv2.COLOR_BGR2RGB)


def render_jpeg(r, cfg: Config = CFG) -> bytes:
    """The panel as JPEG bytes, kept in memory for the dashboard's live view."""
    return cv2.imencode(".jpg", cv2.cvtColor(render(r, cfg), cv2.COLOR_RGB2BGR))[1].tobytes()


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


def draw_agents(frame_bgr, agents):
    ann = frame_bgr.copy()
    for a in agents:
        x1, y1, x2, y2 = a.box
        col = KIND_COLOR.get(a.kind, (180,180,180))
        th  = 3 if a.risk == "critical" else 2 if a.risk == "high" else 1
        cv2.rectangle(ann, (x1,y1), (x2,y2), col, th)
        ttc = f" ttc {a.ttc_s:.1f}s" if a.ttc_s is not None and a.ttc_s < 10 else ""
        lbl = f"#{a.tid} {a.kind} [{a.motion}] {a.dist_m}m{ttc}"
        (tw, fh), _ = cv2.getTextSize(lbl, FONT, 0.38, 1)
        cv2.rectangle(ann, (x1, y1-fh-5), (x1+tw+4, y1), col, -1)
        cv2.putText(ann, lbl, (x1+2, y1-3), FONT, 0.38, (0,0,0), 1)
        cv2.circle(ann, (x2-6, y1+6), 5, RISK_COLOR.get(a.risk,(120,120,120)), -1)
    return ann


def build_panel(r, cfg: Config = CFG):
    frame, (H, W) = r.frame_bgr, r.frame_bgr.shape[:2]
    flow_bgr = flow_to_bgr(r.flow, frame, cfg) if r.flow is not None else np.zeros_like(frame)
    fused    = cv2.addWeighted(frame, 0.60, depth_colormap(r.depth_arr, cfg), 0.25, 0)
    fused    = cv2.addWeighted(fused, 0.85, flow_bgr, 0.15, 0)
    fused    = cv2.addWeighted(fused, 0.75, draw_agents(frame, r.agents), 0.25, 0)

    top = int(H * cfg.openings.band_top_frac)
    bot = int(H * cfg.openings.band_bottom_frac)
    best = best_opening(r.openings)
    for o in r.openings or []:
        colour  = (0, 255, 80) if o is best else (0, 180, 0) if o.wide_enough else (0, 120, 255)
        overlay = fused.copy()
        overlay[top:bot, o.x1_px:o.x2_px] = colour
        fused = cv2.addWeighted(fused, 0.6, overlay, 0.4, 0)
        cv2.putText(fused, f"{o.width_m:.1f}m", (o.x1_px + 4, bot - 6), FONT, 0.45, colour, 1)
    if best is not None:
        cx = (best.x1_px + best.x2_px) // 2
        cv2.arrowedLine(fused, (W//2, H-10), (cx, bot), (0,255,80), 2, tipLength=0.15)

    for y, label in ((top, "BODY BAND"), (bot, "")):
        cv2.line(fused, (0,y), (W,y), (200,200,200), 1)
        cv2.putText(fused, label, (4,y-4), FONT, 0.30, (200,200,200), 1)
    return fused


def build_advisory(r, cfg: Config = CFG):
    W, ah = r.frame_bgr.shape[1], cfg.ui.advisory_height_px
    adv   = np.full((ah, W, 3), 18, dtype=np.uint8)
    lh    = ah // 5
    d     = r.decision
    col   = COMMAND_COLOR[d.command]

    cv2.rectangle(adv, (0,0), (W, lh+8), (28,28,28), -1)
    cv2.putText(adv, f"> {d.command.replace('_',' ').upper()}   {d.detail}", (6, lh), FONT, 0.60, col, 2)
    cv2.line(adv, (0, lh+8), (W, lh+8), col, 2)

    e = r.ego
    cv2.putText(adv, f"  YOU: {e.action.replace('_',' ')} | {e.speed_ms:.2f} m/s | "
                     f"{r.level} conf {d.confidence:.2f}",
                (6, lh*2+4), FONT, 0.44, ACTION_COLOR.get(e.action, (200,200,200)), 1)

    best = best_opening(r.openings)
    if best is not None:
        text, gcol = (f"  OPENING: {best.width_m:.1f}m wide | {best.dist_m:.1f}m clear | "
                      f"{best.direction.upper()}"), (0,220,80)
    elif r.openings is None:
        text, gcol = "  OPENING: not measured", (0,200,255)
    else:
        text, gcol = "  OPENING: none wide enough", (0,60,220)
    cv2.putText(adv, text, (6, lh*3+4), FONT, 0.44, gcol, 1)

    agents = sorted(r.agents, key=lambda a: (RISKS.index(a.risk), a.dist_m))
    if agents:
        a = agents[0]
        cv2.putText(adv, f"  AGENT [{a.risk.upper()}]: {a.kind} {a.motion} at {a.dist_m:.1f}m",
                    (6, lh*4+4), FONT, 0.44, RISK_COLOR[a.risk], 1)
    else:
        cv2.putText(adv, "  AGENT: none", (6, lh*4+4), FONT, 0.44, (80,180,80), 1)

    cv2.line(adv, (0,0), (W,0), (60,60,60), 2)
    return adv
