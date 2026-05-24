import torch
import numpy as np
import cv2
import math
import models
from config import CFG


def compute(prev_bgr, curr_bgr):
    H, W = prev_bgr.shape[:2]
    ph   = (8 - H % 8) % 8
    pw   = (8 - W % 8) % 8

    def to_t(bgr):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        t   = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(models.DEVICE)
        if ph > 0 or pw > 0:
            t = torch.nn.functional.pad(
                t.float(), (0, pw, 0, ph), mode="replicate").to(torch.uint8)
        return t

    t1, t2   = to_t(prev_bgr), to_t(curr_bgr)
    t1n, t2n = models._raft_transforms(t1, t2)
    with torch.no_grad():
        flow_list = models.raft_model(t1n.to(models.DEVICE), t2n.to(models.DEVICE))
    return flow_list[-1][0][:, :H, :W]   # [2,H,W]


def to_bgr_hue_arrows(flow, frame_bgr):
    flow_np = flow.permute(1, 2, 0).cpu().numpy()
    H, W    = flow_np.shape[:2]
    fx, fy  = flow_np[..., 0], flow_np[..., 1]

    angle    = (np.arctan2(fy, fx) + np.pi) / (2 * np.pi)
    mag      = np.sqrt(fx**2 + fy**2)
    mag_norm = np.clip(mag / (np.percentile(mag, 99) + 1e-6), 0, 1)

    hsv         = np.zeros((H, W, 3), dtype=np.uint8)
    hsv[..., 0] = (angle * 179).astype(np.uint8)
    hsv[..., 1] = 220
    hsv[..., 2] = (mag_norm * 255).astype(np.uint8)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    bgr = cv2.addWeighted(frame_bgr, 0.25, bgr, 0.75, 0)

    step  = CFG["flow_arrow_step"]
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


def extract_signals(flow_tensor, depth_arr, H, W):
    flow_np = flow_tensor.permute(1, 2, 0).cpu().numpy()
    fx, fy  = flow_np[..., 0], flow_np[..., 1]
    mag     = np.sqrt(fx**2 + fy**2).astype(np.float32)

    bg_rows            = max(1, int(H * CFG["ego_background_frac"]))
    ego_flow_magnitude = float(mag[:bg_rows, :].mean())

    total_mag       = float(mag.sum()) + 1e-8
    xs              = np.tile(np.arange(W), (H, 1)).astype(np.float32)
    flow_centroid_x = float((mag * xs).sum() / total_mag) / W

    fx_e = float((fx**2).sum())
    fy_e = float((fy**2).sum())
    flow_lateral_ratio = fx_e / (fx_e + fy_e + 1e-8)

    left_fx  = float(fx[:, :W//2].mean())
    right_fx = float(fx[:, W//2:].mean())
    same_dir = (np.sign(left_fx) == np.sign(right_fx)) and \
               (abs(left_fx) > 0.5) and (abs(right_fx) > 0.5)
    rot_mag  = abs(left_fx - right_fx)
    max_pos  = max(abs(left_fx) + abs(right_fx), 1e-8)
    flow_rotation_score = float(1.0 - rot_mag / max_pos) if same_dir else 0.0

    return {
        "ego_flow_magnitude":  round(ego_flow_magnitude, 3),
        "flow_centroid_x":     round(flow_centroid_x, 3),
        "flow_lateral_ratio":  round(flow_lateral_ratio, 3),
        "flow_rotation_score": round(flow_rotation_score, 3),
    }


def derive_ego(flow_signals, depth_arr, speed_history, H, W):
    ego_mag = flow_signals["ego_flow_magnitude"]
    cx_norm = flow_signals["flow_centroid_x"]
    lat_rat = flow_signals["flow_lateral_ratio"]
    rot_sc  = flow_signals["flow_rotation_score"]

    fov_rad   = math.radians(CFG["fov_deg"])
    focal_px  = W / (2 * math.tan(fov_rad / 2))
    med_depth = float(np.clip(np.median(depth_arr), 0.5, 12.0))
    ego_speed = round(ego_mag * med_depth / (focal_px + 1e-8) * 30.0, 3)
    speed_trend = round(ego_speed - speed_history[-1], 3) if speed_history else 0.0

    offset = cx_norm - 0.5
    if abs(offset) < 0.08:   lateral_drift = "straight"
    elif offset > 0.15:      lateral_drift = "strong_left"
    elif offset > 0.08:      lateral_drift = "slight_left"
    elif offset < -0.15:     lateral_drift = "strong_right"
    else:                    lateral_drift = "slight_right"

    action, confidence = _classify_action(
        ego_mag, ego_speed, lat_rat, cx_norm, rot_sc, speed_trend)

    return {
        "ego_speed_ms":        ego_speed,
        "ego_flow_magnitude":  ego_mag,
        "flow_centroid_x":     cx_norm,
        "flow_lateral_ratio":  lat_rat,
        "flow_rotation_score": rot_sc,
        "lateral_drift":       lateral_drift,
        "speed_trend_ms":      speed_trend,
        "action":              action,
        "action_confidence":   confidence,
    }


def _classify_action(ego_mag, ego_speed, lat_ratio, centroid_x, rot_score, speed_trend):
    if ego_mag < CFG["flow_mag_still"]:
        return "standing_still", 0.95
    if ego_speed < 0.15 and speed_trend < -0.25:
        return "stopping", 0.88
    if rot_score > CFG["flow_rotation_thresh"] and ego_mag > CFG["flow_mag_still"]:
        if centroid_x > 0.52:    return "turning_left",  0.78
        elif centroid_x < 0.48:  return "turning_right", 0.78
    is_lateral = (
        lat_ratio > CFG["flow_lateral_thresh"] and
        ego_mag   > CFG["flow_mag_very_slow"]  and
        rot_score < CFG["flow_rotation_thresh"]
    )
    if is_lateral:
        if centroid_x > 0.65:    return "stepping_left",  0.82
        elif centroid_x < 0.35:  return "stepping_right", 0.82
    if ego_mag > CFG["flow_mag_normal"]:      return "walking_fast",      0.90
    elif ego_mag > CFG["flow_mag_slow"]:      return "walking_forward",   0.88
    elif ego_mag > CFG["flow_mag_very_slow"]: return "walking_slow",      0.85
    else:                                     return "walking_very_slow", 0.80