import math

import numpy as np

from walksafe.config import CFG, CameraConfig, EgoConfig


def standing_still():
    return {
        "action":              "standing_still",
        "action_confidence":   0.95,
        "ego_speed_ms":        0.0,
        "lateral_drift":       "straight",
        "speed_trend_ms":      0.0,
        "ego_flow_magnitude":  0.0,
        "flow_centroid_x":     0.5,
        "flow_lateral_ratio":  0.0,
        "flow_rotation_score": 0.0,
    }


def extract_signals(flow, cfg: EgoConfig = CFG.ego):
    H, W   = flow.shape[:2]
    fx, fy = flow[..., 0], flow[..., 1]
    mag    = np.sqrt(fx**2 + fy**2).astype(np.float32)

    bg_rows            = max(1, int(H * cfg.background_frac))
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


def derive_ego(flow_signals, depth_arr, speed_history,
               cfg: EgoConfig = CFG.ego, camera: CameraConfig = CFG.camera):
    W       = depth_arr.shape[1]
    ego_mag = flow_signals["ego_flow_magnitude"]
    cx_norm = flow_signals["flow_centroid_x"]
    lat_rat = flow_signals["flow_lateral_ratio"]
    rot_sc  = flow_signals["flow_rotation_score"]

    fov_rad   = math.radians(camera.fov_deg)
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
        ego_mag, ego_speed, lat_rat, cx_norm, rot_sc, speed_trend, cfg)

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


def _classify_action(ego_mag, ego_speed, lat_ratio, centroid_x, rot_score, speed_trend, cfg):
    if ego_mag < cfg.mag_still:
        return "standing_still", 0.95
    if ego_speed < 0.15 and speed_trend < -0.25:
        return "stopping", 0.88
    if rot_score > cfg.rotation_thresh and ego_mag > cfg.mag_still:
        if centroid_x > 0.52:    return "turning_left",  0.78
        elif centroid_x < 0.48:  return "turning_right", 0.78
    is_lateral = (
        lat_ratio > cfg.lateral_thresh and
        ego_mag   > cfg.mag_very_slow  and
        rot_score < cfg.rotation_thresh
    )
    if is_lateral:
        if centroid_x > 0.65:    return "stepping_left",  0.82
        elif centroid_x < 0.35:  return "stepping_right", 0.82
    if ego_mag > cfg.mag_normal:      return "walking_fast",      0.90
    elif ego_mag > cfg.mag_slow:      return "walking_forward",   0.88
    elif ego_mag > cfg.mag_very_slow: return "walking_slow",      0.85
    else:                             return "walking_very_slow", 0.80
