"""One frame through perception, interpretation and decision."""
import threading
import time
from concurrent.futures import Future, wait
from dataclasses import dataclass, field

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
    depth_age_s: float | None = 0.0   # how old the depth map behind this result is
    timings:   dict[str, float] = field(default_factory=dict)    # milliseconds per stage

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
        timer = _Timer()
        s.frame_idx += 1
        frame = resize(frame_bgr, cfg.models.resize_width)
        q     = quality.check_frame(frame, cfg.quality)
        if not q.ok:
            d = decision.decide([], None, 0.0, s.profile, cfg)
            d = Decision(d.command, "poor visibility", f"frame_rejected:{q.cause} | {d.reason}", 0.0)
            return FrameResult(frame, capture_ts, q, None, None, [], None, s.ego, d, "L1", timer.lap("quality"))
        timer.lap("quality")

        prev_depth = s.depth_arr
        depth      = latest_depth(models, s, frame, capture_ts, cfg)
        timer.lap("depth")
        if depth is None:          # the first depth map is still being computed
            d = decision.decide([], None, 0.0, s.profile, cfg)
            d = Decision(d.command, "measuring depth", f"waiting_for_first_depth | {d.reason}", 0.0)
            return FrameResult(frame, capture_ts, q, None, None, [], None, s.ego, d, "L1", None, timer.laps)

        boxes  = models.detector.track(frame, s.tracker)
        agents = agents_.measure(boxes, depth, capture_ts, s.tracks, s.profile, cfg.agents)
        timer.lap("detection")

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
        timer.lap("flow")

        openings   = openings_.find(depth, agents, s.profile, cfg.openings)
        conf, why  = quality.confidence(agents, cfg.quality, cfg.agents)
        d          = decision.decide(agents, openings, conf, s.profile, cfg)
        if why:
            d = Decision(d.command, d.detail, f"{d.reason} | confidence {conf:.2f}: {why}", d.confidence)
        level = "L1" if conf < cfg.decision.confidence_low else "L0"
        return FrameResult(frame, capture_ts, q, depth, flow, agents, openings, s.ego, d, level,
                           round(capture_ts - s.depth_ts, 2), timer.lap("rules"))


def latest_depth(models: Models, s: Session, frame: np.ndarray, ts: float,
                 cfg: Config = CFG) -> np.ndarray | None:
    """The depth map to use for this frame, refreshing it when it is older than the cap.
    In the background mode this is None until the session's first map is ready."""
    if s.depth_job is not None and s.depth_job.done():
        s.depth_arr, s.depth_ts = s.depth_job.result()      # a fault surfaces here
        s.depth_job = None
    stale = s.depth_arr is None or ts - s.depth_ts > cfg.models.depth_max_age_s
    if stale and not cfg.models.depth_in_background:
        s.depth_arr, s.depth_ts = models.depth.estimate(frame) * s.profile.depth_scale, ts
    elif stale and s.depth_job is None:
        scale, snapshot = s.profile.depth_scale, frame.copy()
        s.depth_job = in_background(lambda: (models.depth.estimate(snapshot) * scale, ts))
    if s.depth_arr is None and s.depth_job is not None:
        # A fast model gives the first map almost at once; a slow one is not waited for.
        wait([s.depth_job], timeout=cfg.models.first_depth_wait_s)
        if s.depth_job.done():
            s.depth_arr, s.depth_ts = s.depth_job.result()
            s.depth_job = None
    return s.depth_arr


def in_background(fn) -> Future:
    future = Future()

    def run():
        try:
            future.set_result(fn())
        except Exception as e:                  # handed to the next frame, which reports it
            future.set_exception(e)

    threading.Thread(target=run, name="depth", daemon=True).start()
    return future


class _Timer:
    def __init__(self):
        self.laps, self.last = {}, time.perf_counter()

    def lap(self, name: str) -> dict[str, float]:
        now = time.perf_counter()
        self.laps[name] = round((now - self.last) * 1000, 1)
        self.last = now
        return self.laps
