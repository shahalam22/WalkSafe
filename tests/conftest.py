import numpy as np

from walksafe.perception import Box, Models


class FakeDepth:
    def __init__(self, metres=4.0):
        self.metres = metres
        self.calls  = 0

    def estimate(self, frame_bgr):
        self.calls += 1
        return np.full(frame_bgr.shape[:2], self.metres, dtype=np.float32)


class FakeDetector:
    def __init__(self, boxes: list[Box] | None = None):
        self.boxes = boxes or []

    def new_tracker(self):
        return object()

    def track(self, frame_bgr, tracker):
        return list(self.boxes)


class FakeFlow:
    def __init__(self, dx=0.0, dy=0.0):
        self.dx, self.dy = dx, dy
        self.calls = 0

    def compute(self, prev_bgr, curr_bgr):
        self.calls += 1
        flow = np.zeros((*curr_bgr.shape[:2], 2), dtype=np.float32)
        flow[..., 0], flow[..., 1] = self.dx, self.dy
        return flow


def fake_models(**kw) -> Models:
    return Models(depth=kw.get("depth", FakeDepth()),
                  detector=kw.get("detector", FakeDetector()),
                  flow=kw.get("flow", FakeFlow()))
