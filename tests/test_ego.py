import math

import numpy as np
import pytest

from walksafe.config import CFG
from walksafe.interpretation.ego import camera_motion, classify, estimate, judge_step

H, W  = 378, 518
FOCAL = CFG.profile.focal_px(W)


def depth_map(seed=0):
    """Blocky depth between 2 and 8 m, like a street with things at different distances."""
    blocks = np.random.default_rng(seed).uniform(2.0, 8.0, (H // 14 + 1, W // 14 + 1))
    return np.kron(blocks, np.ones((14, 14)))[:H, :W].astype(np.float32)


def flow_for(depth, move=(0.0, 0.0, 0.0), yaw_deg=0.0):
    """Exact image motion of static points when the camera moves by `move` (metres,
    x right, z forward) and then turns right by yaw_deg."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)
    x, y   = xs - (W - 1) / 2, ys - (H - 1) / 2
    Z      = depth.astype(np.float64)
    X, Y   = x * Z / FOCAL, y * Z / FOCAL
    X, Y, Z = X - move[0], Y - move[1], Z - move[2]
    t      = math.radians(yaw_deg)
    X, Z   = X * math.cos(t) - Z * math.sin(t), X * math.sin(t) + Z * math.cos(t)
    flow   = np.empty((H, W, 2), dtype=np.float32)
    flow[..., 0] = FOCAL * X / Z - x
    flow[..., 1] = FOCAL * Y / Z - y
    return flow


def ego_for(move=(0, 0, 0), yaw_deg=0.0, dt=0.5, history=()):
    depth = depth_map()
    return estimate(flow_for(depth, move, yaw_deg), depth, dt, FOCAL, list(history))


def test_still_camera_is_standing_still():
    assert ego_for().action == "standing_still"


def test_walking_forward_gives_metric_speed():
    e = ego_for(move=(0, 0, 0.6))
    assert e.action == "walking_forward"
    assert e.speed_ms == pytest.approx(1.2, rel=0.05)


def test_t1_step_left_is_stepping_left():
    e = ego_for(move=(-0.25, 0, 0))
    assert e.action == "stepping_left"
    assert e.lateral_ms == pytest.approx(-0.5, rel=0.05)


def test_step_right_is_stepping_right():
    assert ego_for(move=(0.25, 0, 0)).action == "stepping_right"


def test_turns_are_told_apart_from_steps():
    assert ego_for(yaw_deg=15).action == "turning_right"
    assert ego_for(yaw_deg=-15).action == "turning_left"


def test_t1_mirrored_flow_reads_as_the_opposite_step():
    # A build that flipped the image would report the user's left step as a
    # right step; the setup direction test relies on catching exactly this.
    depth = depth_map()
    flow  = flow_for(depth, move=(-0.25, 0, 0))
    mirrored_flow = flow[:, ::-1].copy()
    mirrored_flow[..., 0] *= -1
    e = estimate(mirrored_flow, depth[:, ::-1].copy(), 0.5, FOCAL, [])
    assert e.action == "stepping_right"


@pytest.mark.parametrize("fps", [1.5, 5, 15])
def test_t4_walking_speed_does_not_depend_on_frame_rate(fps):
    dt = 1 / fps
    e  = ego_for(move=(0, 0, 1.2 * dt), dt=dt)
    assert e.speed_ms == pytest.approx(1.2, rel=0.05)


def test_moving_agents_are_left_out_of_the_fit():
    depth = depth_map()
    flow  = flow_for(depth, move=(0, 0, 0.6))
    flow[100:300, 200:320] = (40.0, 0.0)              # a cyclist sweeping across
    e = estimate(flow, depth, 0.5, FOCAL, [], exclude_boxes=[(200, 100, 320, 300)])
    assert e.action == "walking_forward"


def test_no_measurable_scene_gives_none():
    depth = np.full((H, W), 50.0, dtype=np.float32)      # all beyond max_depth_m
    assert estimate(np.zeros((H, W, 2), np.float32), depth, 0.5, FOCAL, []) is None


def test_slowing_sharply_is_stopping():
    assert classify(0.3, 0.0, 0.0, -0.6) == "stopping"
    assert classify(2.0, 0.0, 0.0, 0.0) == "walking_fast"
    assert classify(0.4, 0.0, 0.0, 0.0) == "walking_slow"


def test_t1_direction_test_measures_the_step_in_metres():
    depth = depth_map()
    left  = judge_step(camera_motion(flow_for(depth, move=(-0.4, 0, 0)), depth, FOCAL), 0.15)
    assert left["verdict"] == "left" and left["lateral_m"] == pytest.approx(-0.4, abs=0.03)
    right = judge_step(camera_motion(flow_for(depth, move=(0.4, 0, 0)), depth, FOCAL), 0.15)
    assert right["verdict"] == "right"
    small = judge_step(camera_motion(flow_for(depth, move=(-0.05, 0, 0)), depth, FOCAL), 0.15)
    assert small["verdict"] == "unclear"
    assert judge_step(None, 0.15)["verdict"] == "unclear"


def test_t1_a_twist_of_the_body_is_not_a_step():
    depth = depth_map()
    assert judge_step(camera_motion(flow_for(depth, yaw_deg=-15), depth, FOCAL), 0.15)["verdict"] == "unclear"


def test_t1_a_mirrored_camera_turns_a_left_step_into_right():
    depth = depth_map()
    flow  = flow_for(depth, move=(-0.4, 0, 0))[:, ::-1].copy()
    flow[..., 0] *= -1
    assert judge_step(camera_motion(flow, depth[:, ::-1].copy(), FOCAL), 0.15)["verdict"] == "right"
