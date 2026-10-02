import numpy as np

from walksafe.interpretation.agents import classify_motion, measure, risk_level
from walksafe.perception import Box


def feed(points, depth=3.0):
    history, motion = {}, None
    for i, (x, y) in enumerate(points):
        motion = classify_motion(1, x, y, i, depth, history)
    return motion


def test_track_is_new_until_four_points():
    assert feed([(100, 100)] * 3) == "new"


def test_small_movement_is_static():
    assert feed([(100, 100), (101, 100), (102, 101), (103, 101)]) == "static"


def test_rightward_movement_is_crossing_right():
    assert feed([(100, 100), (120, 100), (140, 100), (160, 100)]) == "crossing-R"


def test_downward_movement_in_image_is_approaching():
    assert feed([(100, 100), (100, 110), (100, 120), (100, 130)]) == "approaching"


def test_risk_levels():
    assert risk_level("static", 5.0, 0.5) == "critical"
    assert risk_level("approaching", 0.8, None) == "critical"
    assert risk_level("static", 5.0, 1.5) == "high"
    assert risk_level("static", 5.0, 3.0) == "moderate"
    assert risk_level("erratic", 5.0, None) == "moderate"
    assert risk_level("receding", 5.0, None) == "low"


def test_approach_speed_assumes_30_fps():
    # Characterises defect 1, fixed in Phase 1: 0.6 m over 4 frames is taken as
    # 4/30 s whatever the real frame rate was.
    history, box = {}, Box(200, 100, 260, 300, 0, 0.9, 7)
    for d in (5.0, 4.8, 4.6, 4.4):
        dets = measure([box], np.full((378, 518), d, dtype=np.float32), 0, history)
    a = dets[0]
    assert a["approach_speed_ms"] == 4.5
    assert a["ttc_s"] == 0.98
    assert a["risk_level"] == "critical"


def test_untracked_box_is_static_with_no_speed():
    dets = measure([Box(10, 10, 50, 90, 2, 0.5, -1)], np.full((378, 518), 3.0, dtype=np.float32), 1, {})
    assert dets[0]["motion"] == "static"
    assert dets[0]["approach_speed_ms"] == 0.0
    assert dets[0]["name"] == "car"


def test_every_coco_class_becomes_an_agent():
    # Characterises defect 11, fixed in Phase 1.
    dets = measure([Box(10, 10, 50, 90, 56, 0.5, -1)], np.full((378, 518), 3.0, dtype=np.float32), 1, {})
    assert dets[0]["name"] == "chair"
