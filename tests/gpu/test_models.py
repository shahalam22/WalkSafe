"""The real models on a GPU (T2, T3 and NFR-4 smoke checks). Run on Colab:

    python -m pytest -m gpu -q
"""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytestmark = [pytest.mark.gpu,
              pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a CUDA GPU")]

import cv2  # noqa: E402

from walksafe import pipeline  # noqa: E402
from walksafe.config import CFG  # noqa: E402
from walksafe.decision import COMMANDS  # noqa: E402
from walksafe.session import Session  # noqa: E402


@pytest.fixture(scope="module")
def models():
    from walksafe.perception import loader
    return loader.load()


@pytest.fixture(scope="module")
def street():
    from ultralytics.utils import ASSETS
    return pipeline.resize(cv2.imread(str(ASSETS / "bus.jpg")), CFG.models.resize_width)


def shifted(img, dx):
    return cv2.warpAffine(img, np.float32([[1, 0, dx], [0, 1, 0]]), (img.shape[1], img.shape[0]),
                          borderMode=cv2.BORDER_REFLECT)


def test_depth_is_metric_and_plausible(models, street):
    depth = models.depth.estimate(street)
    assert depth.shape == street.shape[:2]
    assert np.isfinite(depth).all() and 0.3 < np.median(depth) < 100
    assert models.depth.last_fov_deg is None or 30 < models.depth.last_fov_deg < 120


def test_fp16_depth_stays_close_to_fp32(models, street):
    from walksafe.perception.depth import DepthModel
    half = DepthModel(CFG.models.depth_model_id, "cuda", fp16=True).estimate(street)
    full = models.depth.estimate(street)
    assert abs(np.median(half) / np.median(full) - 1) < 0.05


def test_t3_people_are_detected_and_keep_their_identity(models, street):
    tracker = models.detector.new_tracker()
    ids = []
    for dx in (0, 4, 8, 12):
        boxes = models.detector.track(shifted(street, dx), tracker)
        ids.append({b.tid for b in boxes if b.cls == 0 and b.tid >= 0})
    assert ids[-1] and ids[-1] == ids[-2] == ids[-3]


def test_t3_each_session_tracks_on_its_own(models, street):
    # Track ids come from one counter shared by every tracker, so separate
    # sessions never share an id; each tracker still has its own tracks.
    a, b = models.detector.new_tracker(), models.detector.new_tracker()
    for _ in range(3):
        ids_a = {box.tid for box in models.detector.track(street, a) if box.tid >= 0}
    ids_b = {box.tid for box in models.detector.track(street, b) if box.tid >= 0}
    assert ids_a and not ids_a & ids_b


def test_raft_recovers_a_known_shift(models, street):
    flow = models.flow.compute(street, shifted(street, 3))
    assert abs(float(np.median(flow[..., 0])) - 3) < 0.5
    assert abs(float(np.median(flow[..., 1]))) < 0.5


def test_full_pipeline_gives_one_command_with_timings(models, street):
    s = Session(models.detector.new_tracker())
    for i, dx in enumerate((0, 3, 6)):
        r = pipeline.process(models, s, shifted(street, dx), 1000.0 + 0.5 * i)
    assert r.decision.command in COMMANDS
    assert set(r.timings) == {"quality", "depth", "detection", "flow", "rules"}
