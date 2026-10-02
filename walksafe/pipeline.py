"""One frame through perception, interpretation and decision."""
from dataclasses import dataclass

import cv2
import numpy as np

from walksafe import decision
from walksafe.config import CFG, Config
from walksafe.decision import Decision
from walksafe.interpretation import agents as agents_
from walksafe.interpretation import ego as ego_
from walksafe.interpretation import openings as openings_
from walksafe.interpretation import quality
from walksafe.interpretation.agents import Agent
from walksafe.interpretation.ego import Ego
from walksafe.interpretation.openings import Opening
from walksafe.interpretation.quality import FrameQuality
from walksafe.perception import Models
from walksafe.session import Session


@dataclass
class FrameResult:
    frame_bgr: np.ndarray
    capture_ts: float
    quality:   FrameQuality
    depth_arr: np.ndarray | None
    flow:      np.ndarray | None
    agents:    list[Agent]
    openings:  list[Opening] | None
    ego:       Ego
    decision:  Decision
    level:     str            # "L0", or "L1" when visibility or confidence is poor

    @property
    def phrase(self) -> str:
        return decision.phrase(self.decision.command)


def resize(frame, width):
    h, w  = frame.shape[:2]
    new_w = (width // 14) * 14
    new_h = int(h * new_w / w)
    new_h = (new_h // 14) * 14
    return cv2.resize(frame, (new_w, new_h))


def process(models: Models, s: Session, frame_bgr: np.ndarray, capture_ts: float,
            cfg: Config = CFG) -> FrameResult:
    """capture_ts is in seconds on the capturing device's clock and must increase."""
    with s.lock:
        s.frame_idx += 1
        frame = resize(frame_bgr, cfg.models.resize_width)
        q     = quality.check_frame(frame, cfg.quality)
        if not q.ok:
            d = decision.decide([], None, 0.0, s.profile, cfg)
            d = Decision(d.command, "poor visibility", f"frame_rejected:{q.cause} | {d.reason}", 0.0)
            return FrameResult(frame, capture_ts, q, None, None, [], None, s.ego, d, "L1")

        prev_depth = s.depth_arr
        if s.depth_arr is None or capture_ts - s.depth_ts > cfg.models.depth_max_age_s:
            s.depth_arr = models.depth.estimate(frame) * s.profile.depth_scale
            s.depth_ts  = capture_ts
        depth = s.depth_arr

        boxes  = models.detector.track(frame, s.tracker)
        agents = agents_.measure(boxes, depth, capture_ts, s.tracks, s.profile, cfg.agents)

        flow = None
        dt   = capture_ts - s.prev_ts
        if s.prev_frame is not None and s.prev_frame.shape == frame.shape and dt <= cfg.ego.max_interval_s:
            flow = models.flow.compute(s.prev_frame, frame)
            e = ego_.estimate(flow, prev_depth, dt, s.profile.focal_px(frame.shape[1]),
                              s.speed_history, [a.box for a in agents], cfg.ego)
            if e is not None:
                s.ego = e
                s.speed_history = (s.speed_history + [e.speed_ms])[-cfg.ego.speed_history_len:]
        s.prev_frame, s.prev_ts = frame, capture_ts

        openings   = openings_.find(depth, agents, s.profile, cfg.openings)
        conf, why  = quality.confidence(agents, cfg.quality, cfg.agents)
        d          = decision.decide(agents, openings, conf, s.profile, cfg)
        if why:
            d = Decision(d.command, d.detail, f"{d.reason} | confidence {conf:.2f}: {why}", d.confidence)
        level = "L1" if conf < cfg.decision.confidence_low else "L0"
        return FrameResult(frame, capture_ts, q, depth, flow, agents, openings, s.ego, d, level)
