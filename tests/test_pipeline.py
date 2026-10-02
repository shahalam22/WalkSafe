import numpy as np
from conftest import FakeDepth, FakeFlow, fake_models

from walksafe import pipeline
from walksafe.decision import COMMANDS
from walksafe.session import Session


def frame(h=480, w=640):
    return np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)


def test_frame_is_resized_to_a_multiple_of_14():
    r = pipeline.process(fake_models(), Session(), frame())
    assert r.frame_bgr.shape[1] == 518
    assert r.frame_bgr.shape[0] % 14 == 0


def test_depth_is_refreshed_every_fifth_frame():
    # Characterises defect 2, fixed in Phase 1: by frame count, not by age.
    depth, s = FakeDepth(), Session()
    models = fake_models(depth=depth)
    for _ in range(10):
        pipeline.process(models, s, frame())
    assert depth.calls == 3            # frames 1, 5 and 10


def test_flow_starts_on_the_second_frame():
    flow, s = FakeFlow(), Session()
    models = fake_models(flow=flow)
    r1 = pipeline.process(models, s, frame())
    r2 = pipeline.process(models, s, frame())
    assert r1.flow is None and r2.flow is not None
    assert flow.calls == 1


def test_one_valid_command_per_frame():
    r = pipeline.process(fake_models(), Session(), frame())
    assert r.command in COMMANDS
    assert r.phrase
