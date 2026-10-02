import numpy as np
import pytest
from conftest import FakeDepth, FakeDetector, FakeFlow, fake_models

from walksafe import pipeline
from walksafe.config import Profile
from walksafe.decision import COMMANDS
from walksafe.perception import Box
from walksafe.session import Session


def frame(seed=0):
    return np.random.default_rng(seed).integers(0, 255, (480, 640, 3), dtype=np.uint8)


def session(models, **kw):
    return Session(models.detector.new_tracker(), **kw)


def run(models, s, times):
    return [pipeline.process(models, s, frame(i), t) for i, t in enumerate(times)]


def test_frame_is_resized_to_a_multiple_of_14():
    m = fake_models()
    (r,) = run(m, session(m), [0.0])
    assert r.frame_bgr.shape[1] == 518 and r.frame_bgr.shape[0] % 14 == 0


def test_depth_is_refreshed_by_age_not_frame_count():
    depth = FakeDepth()
    m = fake_models(depth=depth)
    run(m, session(m), [0.0, 0.2, 0.39, 0.5, 0.6, 0.95])
    assert depth.calls == 3                         # at 0.0, 0.5 and 0.95 s


def test_depth_scale_from_setup_is_applied():
    m = fake_models(depth=FakeDepth(4.0))
    (r,) = run(m, session(m, profile=Profile(depth_scale=1.25)), [0.0])
    assert float(r.depth_arr.mean()) == pytest.approx(5.0)


def test_each_session_has_its_own_tracker():
    m = fake_models()
    assert session(m).tracker is not session(m).tracker


def test_flow_needs_a_recent_previous_frame():
    flow = FakeFlow()
    m = fake_models(flow=flow)
    results = run(m, session(m), [0.0, 0.5, 5.0])
    assert [r.flow is not None for r in results] == [False, True, False]


def test_dark_frame_is_rejected_without_running_the_models():
    depth = FakeDepth()
    m = fake_models(depth=depth)
    r = pipeline.process(m, session(m), np.zeros((480, 640, 3), np.uint8), 0.0)
    assert depth.calls == 0
    assert r.decision.command == "slow_down" and r.level == "L1"
    assert r.decision.reason.startswith("frame_rejected:dark")


def test_one_valid_command_per_frame():
    m = fake_models(detector=FakeDetector([Box(200, 150, 260, 350, 0, 0.9, 4)]))
    for r in run(m, session(m), [0.0, 0.5, 1.0, 1.5]):
        assert r.decision.command in COMMANDS and r.phrase


def test_new_close_agent_lowers_the_level_to_l1():
    m = fake_models(depth=FakeDepth(2.0), detector=FakeDetector([Box(200, 150, 260, 350, 0, 0.9, -1)]))
    (r,) = run(m, session(m), [0.0])
    assert r.level == "L1" and "not yet tracked" in r.decision.reason
