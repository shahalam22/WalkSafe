import numpy as np
import pytest

from walksafe.config import CFG
from walksafe.interpretation.agents import (
    classify_motion,
    fit_speeds,
    measure,
    risk_level,
    time_to_collision,
    time_to_path,
)
from walksafe.perception import Box

H, W  = 378, 518
FOCAL = CFG.profile.focal_px(W)


def scene(dist, lateral=0.0, background=12.0, tid=1, cls=0):
    """Depth map and box for a 0.5 m wide, 1.7 m tall person at (lateral, dist)."""
    cx     = W / 2 + lateral * FOCAL / dist
    half_w = 0.25 * FOCAL / dist
    height = 1.7 * FOCAL / dist
    box    = Box(int(cx - half_w), int(H - 20 - height), int(cx + half_w), H - 20, cls, 0.9, tid)
    depth  = np.full((H, W), background, dtype=np.float32)
    depth[max(box.y1, 0):box.y2, max(box.x1, 0):box.x2] = dist
    return depth, box


def walk(fps, seconds, dist0, approach=0.0, lateral0=0.0, lateral_speed=0.0):
    tracks, agents = {}, []
    for i in range(int(seconds * fps) + 1):
        t = i / fps
        depth, box = scene(dist0 - approach * t, lateral0 + lateral_speed * t)
        agents = measure([box], depth, 1000.0 + t, tracks)
    return agents[0]


@pytest.mark.parametrize("fps", [1.5, 5, 15])
def test_t4_approach_speed_and_ttc_do_not_depend_on_frame_rate(fps):
    a = walk(fps, 2.0, dist0=7.0, approach=1.0)
    assert a.motion == "approaching"
    assert a.approach_speed_ms == pytest.approx(1.0, abs=0.08)
    assert a.ttc_s == pytest.approx(a.dist_m / 1.0, rel=0.1)


@pytest.mark.parametrize("fps", [1.5, 5, 15])
def test_t4_crossing_speed_does_not_depend_on_frame_rate(fps):
    a = walk(fps, 2.0, dist0=5.0, lateral0=-2.0, lateral_speed=0.8)
    assert a.motion == "crossing_right"
    assert a.lateral_speed_ms == pytest.approx(0.8, abs=0.08)


def test_track_is_new_until_it_has_enough_history():
    tracks = {}
    depth, box = scene(4.0)
    assert measure([box], depth, 0.0, tracks)[0].motion == "new"
    assert measure([box], depth, 0.1, tracks)[0].motion == "new"
    assert measure([box], depth, 0.4, tracks)[0].motion == "static"


def test_motion_classes():
    assert classify_motion(None, None) == "new"
    assert classify_motion(0.0, 0.0) == "static"
    assert classify_motion(1.0, 0.1) == "approaching"
    assert classify_motion(-1.0, 0.1) == "receding"
    assert classify_motion(0.1, 1.0) == "crossing_right"
    assert classify_motion(0.1, -1.0) == "crossing_left"


def test_speeds_come_from_timestamps_not_point_count():
    from walksafe.interpretation.agents import TrackPoint
    uneven = [TrackPoint(0.0, 6.0, 0), TrackPoint(0.2, 5.8, 0), TrackPoint(1.5, 4.5, 0)]
    approach, lateral = fit_speeds(uneven)
    assert approach == pytest.approx(1.0)
    assert lateral == pytest.approx(0.0)


def test_ttc_only_when_closing():
    assert time_to_collision(4.0, 2.0) == 2.0
    assert time_to_collision(4.0, -1.0) is None
    assert time_to_collision(4.0, None) is None
    assert time_to_collision(4.0, 0.01) is None


def test_time_to_path_for_an_agent_moving_toward_the_corridor():
    assert time_to_path(2.0, -1.0, 0.5) == pytest.approx(1.5)
    assert time_to_path(2.0, 1.0, 0.5) is None
    assert time_to_path(0.2, 1.0, 0.5) == 0.0


def test_risk_levels():
    assert risk_level("static", 5.0, 0.5) == "critical"
    assert risk_level("approaching", 0.8, None) == "critical"
    assert risk_level("static", 0.8, None) == "low"
    assert risk_level("approaching", 5.0, 1.5) == "high"
    assert risk_level("approaching", 5.0, 3.0) == "moderate"
    assert risk_level("receding", 5.0, None) == "low"


def test_only_agent_classes_are_kept():
    depth, box = scene(3.0, cls=56)            # COCO "chair"
    assert measure([box], depth, 0.0, {}) == []


def test_untracked_detection_is_still_an_agent_without_speed():
    depth, box = scene(3.0, tid=-1)
    a = measure([box], depth, 0.0, {})[0]
    assert a.motion == "new" and a.approach_speed_ms is None and a.ttc_s is None
    assert a.dist_m == pytest.approx(3.0)


def test_side_follows_the_image_and_is_never_mirrored():
    for lateral, side in ((-1.2, "left"), (0.0, "ahead"), (1.2, "right")):    # inside a 45-degree view
        depth, box = scene(4.0, lateral)
        assert measure([box], depth, 0.0, {})[0].side == side


def test_old_tracks_are_forgotten():
    tracks = {}
    depth, box = scene(4.0)
    measure([box], depth, 0.0, tracks)
    measure([], depth, CFG.agents.forget_after_s + 1, tracks)
    assert tracks == {}


def test_depth_spread_ignores_the_background_inside_the_box():
    depth, box = scene(3.0, background=10.0)
    depth[box.y1:box.y2, box.x1:box.x1 + 5] = 10.0     # background showing at the box edge
    assert measure([box], depth, 0.0, {})[0].dist_sigma < CFG.quality.depth_sigma_reliable
