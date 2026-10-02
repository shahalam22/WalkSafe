import numpy as np
from conftest import fake_models

from walksafe import pipeline
from walksafe.session import Session
from walksafe.ui import diagnostic


def test_panel_is_the_frame_plus_a_170_px_advisory_strip():
    s = Session()
    f = np.zeros((480, 640, 3), dtype=np.uint8)
    pipeline.process(fake_models(), s, f)
    r = pipeline.process(fake_models(), s, f)
    img = diagnostic.render(r, s.track_history)
    assert img.shape == (r.frame_bgr.shape[0] + 170, 518, 3)
