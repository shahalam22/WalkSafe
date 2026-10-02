"""Agents: motion, approach speed, time to collision and risk (FR-4 to FR-6).

Speeds are fitted against the frames' capture times, never a frame count, so
they come out the same at any frame rate (FR-5).
"""
from collections import deque
from dataclasses import dataclass

import numpy as np

from walksafe.config import CFG, AgentConfig, Profile
from walksafe.perception import Box

NAMES = {0: "person", 1: "cyclist", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
RISKS = ("critical", "high", "moderate", "low")


@dataclass(frozen=True)
class TrackPoint:
    ts:        float
    dist_m:    float
    lateral_m: float          # positive = to the user's right


@dataclass(frozen=True)
class Agent:
    tid:               int    # -1 until the tracker confirms it
    kind:              str
    box:               tuple[int, int, int, int]
    dist_m:            float
    dist_sigma:        float  # spread of the depth patch relative to its distance
    lateral_m:         float
    side:              str    # left / ahead / right
    in_path:           bool   # overlaps the corridor the user needs
    motion:            str    # new / static / approaching / receding / crossing_left / crossing_right
    approach_speed_ms: float | None
    lateral_speed_ms:  float | None
    ttc_s:             float | None
    path_time_s:       float | None   # a crossing agent's time to reach the user's corridor
    risk:              str
    track_points:      int


Tracks = dict[int, deque]


def measure(boxes: list[Box], depth_arr: np.ndarray, ts: float, tracks: Tracks,
            profile: Profile = CFG.profile, cfg: AgentConfig = CFG.agents) -> list[Agent]:
    forget_old_tracks(tracks, ts, cfg)
    W         = depth_arr.shape[1]
    focal     = profile.focal_px(W)
    half_path = profile.needed_width_m / 2
    agents    = []

    for b in boxes:
        if b.cls not in NAMES:
            continue
        dist, sigma = box_distance(depth_arr, b, cfg)
        left_m      = (b.x1 - W / 2) / focal * dist
        right_m     = (b.x2 - W / 2) / focal * dist
        lateral     = (left_m + right_m) / 2
        in_path     = left_m < half_path and right_m > -half_path
        side        = "ahead" if in_path else ("right" if lateral > 0 else "left")

        points = remember(tracks, b.tid, TrackPoint(ts, dist, lateral), cfg) if b.tid >= 0 else []
        approach, lat_speed = fit_speeds(points, cfg)
        motion = classify_motion(approach, lat_speed, cfg)
        ttc    = time_to_collision(dist, approach, cfg)

        agents.append(Agent(
            tid=b.tid, kind=NAMES[b.cls], box=(b.x1, b.y1, b.x2, b.y2),
            dist_m=round(dist, 2), dist_sigma=round(sigma, 3),
            lateral_m=round(lateral, 2), side=side, in_path=in_path, motion=motion,
            approach_speed_ms=_round(approach), lateral_speed_ms=_round(lat_speed),
            ttc_s=_round(ttc), path_time_s=_round(time_to_path(lateral, lat_speed, half_path)),
            risk=risk_level(motion, dist, ttc, cfg), track_points=len(points),
        ))
    return agents


def box_distance(depth_arr, b: Box, cfg: AgentConfig = CFG.agents) -> tuple[float, float]:
    """Near percentile of the lower part of the box, where the agent meets the ground."""
    H, W  = depth_arr.shape
    top   = b.y2 - int((b.y2 - b.y1) * cfg.box_lower_frac)
    patch = depth_arr[max(top, 0):min(b.y2, H), max(b.x1, 0):min(b.x2, W)]
    if patch.size == 0:
        patch = depth_arr[max(min(b.y2, H) - 1, 0), max(b.x1, 0):max(min(b.x2, W), 1)]
    dist = float(np.percentile(patch, cfg.dist_percentile))
    # Spread over the agent itself; the box also holds background, which is far away.
    near = patch[patch <= dist + cfg.foreground_depth_m]
    return dist, float(np.std(near)) / max(dist, 1e-6)


def remember(tracks: Tracks, tid: int, point: TrackPoint, cfg: AgentConfig = CFG.agents) -> list[TrackPoint]:
    points = tracks.setdefault(tid, deque())
    points.append(point)
    while points[0].ts < point.ts - cfg.motion_window_s:
        points.popleft()
    return list(points)


def forget_old_tracks(tracks: Tracks, ts: float, cfg: AgentConfig = CFG.agents) -> None:
    for tid in [t for t, pts in tracks.items() if pts[-1].ts < ts - cfg.forget_after_s]:
        del tracks[tid]


def fit_speeds(points: list[TrackPoint], cfg: AgentConfig = CFG.agents) -> tuple[float | None, float | None]:
    """Approach speed (positive = closing) and lateral speed, in m/s, from a line fit over time."""
    if len(points) < cfg.min_track_points or points[-1].ts - points[0].ts < cfg.min_track_span_s:
        return None, None
    t = np.array([p.ts for p in points]) - points[0].ts
    approach = -np.polyfit(t, [p.dist_m for p in points], 1)[0]
    lateral  =  np.polyfit(t, [p.lateral_m for p in points], 1)[0]
    return float(approach), float(lateral)


def classify_motion(approach: float | None, lateral: float | None, cfg: AgentConfig = CFG.agents) -> str:
    if approach is None:
        return "new"
    if abs(lateral) >= cfg.crossing_speed_ms and abs(lateral) > abs(approach):
        return "crossing_right" if lateral > 0 else "crossing_left"
    if approach >= cfg.approach_speed_ms:
        return "approaching"
    if approach <= -cfg.approach_speed_ms:
        return "receding"
    return "static"


def time_to_collision(dist_m: float, approach: float | None, cfg: AgentConfig = CFG.agents) -> float | None:
    if approach is None or approach < cfg.ttc_min_closing_ms:
        return None
    return min(dist_m / approach, cfg.ttc_max_s)


def time_to_path(lateral_m: float, lateral_speed: float | None, half_path: float) -> float | None:
    outside = abs(lateral_m) - half_path
    if outside <= 0:
        return 0.0
    if lateral_speed is None or lateral_m * lateral_speed >= 0:     # not moving toward the path
        return None
    return outside / abs(lateral_speed)


def risk_level(motion: str, dist_m: float, ttc_s: float | None, cfg: AgentConfig = CFG.agents) -> str:
    if ttc_s is not None and ttc_s < cfg.ttc_critical_s:                return "critical"
    if dist_m < cfg.critical_distance_m and motion == "approaching":   return "critical"
    if ttc_s is not None and ttc_s < cfg.ttc_high_s:                    return "high"
    if ttc_s is not None and ttc_s < cfg.ttc_moderate_s:                return "moderate"
    return "low"


def _round(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)
