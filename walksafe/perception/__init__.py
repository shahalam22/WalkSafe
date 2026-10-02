"""The three models, each behind a small Protocol so tests can pass fakes (NFR-16)."""
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Box:
    x1:   int
    y1:   int
    x2:   int
    y2:   int
    cls:  int
    conf: float
    tid:  int        # -1 when the tracker gave no identity


class DepthEstimator(Protocol):
    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Depth in metres, same height and width as the frame."""


class Detector(Protocol):
    def track(self, frame_bgr: np.ndarray) -> list[Box]: ...


class FlowEstimator(Protocol):
    def compute(self, prev_bgr: np.ndarray, curr_bgr: np.ndarray) -> np.ndarray:
        """Optical flow in pixels, shape (H, W, 2)."""


@dataclass
class Models:
    depth:    DepthEstimator
    detector: Detector
    flow:     FlowEstimator
