"""The user's own motion, from optical flow and the depth map.

A static point at depth Z, seen at (x, y) from the image centre in the first
frame, lands at (x', y') = (x + u, y + v) in the second. If the camera moves
by T = (Tx, Ty, Tz) and turns by w = (wx, wy, wz), then

    u = (x' Tz - f Tx) / Z + (x y / f) wx - (f + x^2 / f) wy + y wz
    v = (y' Tz - f Ty) / Z + (f + y^2 / f) wx - (x y / f) wy - x wz

The translation part is exact for any step size, which matters at 1-2 fps;
the rotation part is the usual small-angle form. Both are linear in the six
unknowns, so a least-squares fit over a grid of points gives them directly,
and because the depth is metric, so is T. Signs: x to the right, y down,
z forward; wy > 0 is a turn to the right. Left and right therefore come from
the direction of the flow, never from where it is concentrated (NFR-6).
"""
import math
from dataclasses import dataclass

import numpy as np

from walksafe.config import CFG, EgoConfig


@dataclass(frozen=True)
class Ego:
    action:         str
    speed_ms:       float     # forward
    lateral_ms:     float     # positive = moving to the right
    yaw_rate_dps:   float     # positive = turning to the right
    speed_trend_ms: float


STILL = Ego("standing_still", 0.0, 0.0, 0.0, 0.0)


def estimate(flow: np.ndarray, depth_arr: np.ndarray, dt: float, focal: float,
             speed_history: list[float], exclude_boxes=(), cfg: EgoConfig = CFG.ego) -> Ego | None:
    """depth_arr belongs to the first frame of the pair. None when there is too little static scene."""
    motion = camera_motion(flow, depth_arr, focal, exclude_boxes, cfg)
    if motion is None or dt <= 0:
        return None
    tx, _, tz, _, wy, _ = motion
    speed   = tz / dt
    lateral = tx / dt
    yaw_dps = math.degrees(wy) / dt
    trend   = speed - speed_history[-1] if speed_history else 0.0
    return Ego(classify(speed, lateral, yaw_dps, trend, cfg),
               round(speed, 3), round(lateral, 3), round(yaw_dps, 1), round(trend, 3))


def camera_motion(flow, depth_arr, focal, exclude_boxes=(), cfg: EgoConfig = CFG.ego):
    """(Tx, Ty, Tz, wx, wy, wz) between the two frames, in metres and radians."""
    H, W = depth_arr.shape
    keep = np.zeros((H, W), dtype=bool)
    keep[::cfg.grid_step_px, ::cfg.grid_step_px] = True
    for x1, y1, x2, y2 in exclude_boxes:          # moving agents break the static-scene model
        keep[max(y1, 0):y2, max(x1, 0):x2] = False
    keep &= (depth_arr >= cfg.min_depth_m) & (depth_arr <= cfg.max_depth_m)

    ys, xs = np.nonzero(keep)
    if len(xs) < cfg.min_points:
        return None
    Z    = depth_arr[ys, xs].astype(np.float64)
    u, v = flow[ys, xs, 0].astype(np.float64), flow[ys, xs, 1].astype(np.float64)
    x    = xs - (W - 1) / 2
    y    = ys - (H - 1) / 2
    f    = focal
    zero = np.zeros_like(Z)

    rows_u = np.stack([-f / Z, zero, (x + u) / Z, x * y / f, -(f + x * x / f),  y], axis=1)
    rows_v = np.stack([zero, -f / Z, (y + v) / Z, f + y * y / f, -x * y / f,   -x], axis=1)
    A = np.vstack([rows_u, rows_v])
    b = np.concatenate([u, v])
    return np.linalg.lstsq(A, b, rcond=None)[0]


def classify(speed, lateral, yaw_dps, trend, cfg: EgoConfig = CFG.ego) -> str:
    if abs(yaw_dps) >= cfg.turn_rate_dps:
        return "turning_right" if yaw_dps > 0 else "turning_left"
    if abs(lateral) >= cfg.step_speed_ms and abs(lateral) > abs(speed):
        return "stepping_right" if lateral > 0 else "stepping_left"
    if trend <= cfg.stopping_trend_ms and speed < cfg.slow_speed_ms:
        return "stopping"
    if speed < cfg.still_speed_ms:
        return "standing_still"
    if speed < cfg.slow_speed_ms:
        return "walking_slow"
    if speed < cfg.fast_speed_ms:
        return "walking_forward"
    return "walking_fast"
