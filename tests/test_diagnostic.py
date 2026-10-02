import numpy as np
from conftest import FakeDetector, fake_models

from walksafe import pipeline
from walksafe.config import CFG
from walksafe.perception import Box
from walksafe.session import Session
from walksafe.ui import diagnostic


def test_panel_is_the_frame_plus_the_advisory_strip():
    m = fake_models(detector=FakeDetector([Box(200, 150, 260, 350, 0, 0.9, 4)]))
    s = Session(m.detector.new_tracker())
    f = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    pipeline.process(m, s, f, 0.0)
    r = pipeline.process(m, s, f, 0.5)
    img = diagnostic.render(r)
    assert img.shape == (r.frame_bgr.shape[0] + CFG.ui.advisory_height_px, 518, 3)


def test_rejected_frame_still_renders():
    m = fake_models()
    r = pipeline.process(m, Session(m.detector.new_tracker()), np.zeros((480, 640, 3), np.uint8), 0.0)
    assert diagnostic.render(r).shape[1] == 518
