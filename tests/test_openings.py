import numpy as np
import pytest

from walksafe.config import CFG, Profile
from walksafe.interpretation.agents import Agent
from walksafe.interpretation.openings import best_opening, find

H, W  = 378, 518
FOCAL = CFG.profile.focal_px(W)


def street(far=10.0):
    return np.full((H, W), far, dtype=np.float32)


def obstacle(depth, x1, x2, dist):
    depth[:, x1:x2] = dist
    return depth


def px(metres_from_centre, dist):
    return int(W / 2 + metres_from_centre * FOCAL / dist)


def test_t5_blank_wall_has_no_opening():
    assert find(street(far=1.5)) == []
    assert best_opening(find(street(far=1.5))) is None


def test_t5_clear_path_is_one_wide_opening_ahead():
    (o,) = find(street())
    assert o.direction == "ahead" and o.wide_enough
    # Fully open view: width is measured at the minimum free distance (conservative).
    assert o.width_m == pytest.approx(W / FOCAL * CFG.openings.min_free_distance_m, abs=0.02)


def test_t5_blocked_ahead_with_a_clear_right_side():
    depth = obstacle(street(), 0, px(0.8, 2.0), 2.0)
    (o,) = find(depth)
    assert o.direction == "right" and o.offset_m > 0


def test_t5_narrow_gap_depends_on_shoulder_width():
    # Two parked scooters 3 m away, inside the look-ahead, with a 0.6 m gap between them.
    depth = obstacle(obstacle(street(), 0, px(-0.3, 3.0), 3.0), px(0.3, 3.0), W, 3.0)
    (o,) = find(depth, profile=Profile(shoulder_width_m=0.45, clearance_margin_m=0.30))
    assert o.width_m == pytest.approx(0.6, abs=0.03)
    assert not o.wide_enough
    (o,) = find(depth, profile=Profile(shoulder_width_m=0.40, clearance_margin_m=0.10))
    assert o.wide_enough and o.direction == "ahead"


def test_t5_width_is_in_metres_at_the_bounding_obstacles():
    near = obstacle(obstacle(street(), 0, px(-0.5, 2.0), 2.0), px(0.5, 2.0), W, 2.0)
    far  = obstacle(obstacle(street(), 0, px(-0.5, 3.2), 3.2), px(0.5, 3.2), W, 3.2)
    assert find(near)[0].width_m == pytest.approx(1.0, abs=0.03)
    assert find(far)[0].width_m == pytest.approx(1.0, abs=0.03)


def test_obstacles_beyond_the_look_ahead_do_not_close_the_path():
    depth = obstacle(street(), 0, W, CFG.openings.min_free_distance_m + 1.0)
    assert find(depth)[0].direction == "ahead"


def test_detected_agents_block_their_columns():
    person = Agent(tid=1, kind="person", box=(px(-0.3, 2.0), 100, px(0.3, 2.0), 300), dist_m=2.0,
                   dist_sigma=0.0, lateral_m=0.0, side="ahead", in_path=True, motion="static",
                   approach_speed_ms=0.0, lateral_speed_ms=0.0, ttc_s=None, path_time_s=0.0,
                   risk="low", track_points=5)
    openings = find(street(), [person])
    assert [o.direction for o in openings] == ["left", "right"]


def test_best_opening_prefers_ahead_then_the_nearest_side():
    depth = obstacle(street(), px(-0.3, 3.0), px(0.3, 3.0), 3.0)      # blocked straight ahead
    openings = find(depth)
    assert {o.direction for o in openings} == {"left", "right"}
    best = best_opening(openings)
    assert abs(best.offset_m) == min(abs(o.offset_m) for o in openings)
    assert best_opening(find(street())).direction == "ahead"
    assert best_opening(None) is None
