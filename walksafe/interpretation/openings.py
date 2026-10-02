"""Walkable openings, measured in metres (FR-7) and compared against the user's width (FR-8).

A column of the image is open when nothing at body height is nearer than an
absolute free distance. Columns covered by a detected agent are only as free
as that agent is far. Each run of open columns is an opening; its width is
measured at the distance of whatever bounds it, which is where the user has
to squeeze past.
"""
from dataclasses import dataclass

import numpy as np

from walksafe.config import CFG, OpeningConfig, Profile


@dataclass(frozen=True)
class Opening:
    x1_px:       int
    x2_px:       int
    width_m:     float
    dist_m:      float      # free distance through the opening
    offset_m:    float      # lateral offset of its centre, positive = right
    direction:   str        # left / ahead / right
    wide_enough: bool


def free_distance(depth_arr: np.ndarray, agents=(), cfg: OpeningConfig = CFG.openings) -> np.ndarray:
    """Distance to the nearest thing at body height, per image column."""
    H, W = depth_arr.shape
    band = depth_arr[int(H * cfg.band_top_frac):int(H * cfg.band_bottom_frac), :]
    free = np.minimum(np.percentile(band, cfg.free_percentile, axis=0), cfg.max_range_m)
    for a in agents:
        x1, x2 = max(a.box[0], 0), min(a.box[2], W)
        free[x1:x2] = np.minimum(free[x1:x2], a.dist_m)
    return free


def find(depth_arr: np.ndarray, agents=(), profile: Profile = CFG.profile,
         cfg: OpeningConfig = CFG.openings) -> list[Opening]:
    free      = free_distance(depth_arr, agents, cfg)
    open_cols = np.concatenate([[False], free >= cfg.min_free_distance_m, [False]])
    edges     = np.flatnonzero(np.diff(open_cols.astype(np.int8)))
    return [_measure(free, x1, x2, profile, cfg)
            for x1, x2 in zip(edges[::2], edges[1::2], strict=True)
            if x2 - x1 >= cfg.min_width_px]


def best_opening(openings: list[Opening] | None) -> Opening | None:
    """The opening to steer for: straight ahead if possible, else the nearest to the side."""
    safe = [o for o in openings or [] if o.wide_enough]
    if not safe:
        return None
    return min(safe, key=lambda o: (o.direction != "ahead", abs(o.offset_m), -o.width_m))


def _measure(free, x1, x2, profile, cfg) -> Opening:
    W      = len(free)
    focal  = profile.focal_px(W)
    bounds = [free[x] for x in (x1 - 1, x2) if 0 <= x < W]
    at_m   = float(min(bounds)) if bounds else cfg.min_free_distance_m

    width_m  = (x2 - x1) / focal * at_m
    offset_m = ((x1 + x2) / 2 - W / 2) / focal * at_m
    half_px  = profile.needed_width_m / 2 * focal / at_m
    if x1 <= W / 2 - half_px and x2 >= W / 2 + half_px:
        direction = "ahead"
    else:
        direction = "right" if offset_m > 0 else "left"

    return Opening(
        x1_px=int(x1), x2_px=int(x2), width_m=round(width_m, 2),
        dist_m=round(float(np.median(free[x1:x2])), 2), offset_m=round(offset_m, 2),
        direction=direction, wide_enough=width_m >= profile.needed_width_m,
    )
