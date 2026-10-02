"""One frame through perception, interpretation and decision."""
from dataclasses import dataclass

import cv2
import numpy as np

from walksafe import decision
from walksafe.config import CFG, Config
from walksafe.interpretation import agents, ego, openings
from walksafe.perception import Models
from walksafe.session import Session


@dataclass
class FrameResult:
    frame_bgr: np.ndarray
    depth_arr: np.ndarray
    flow:      np.ndarray | None
    dets:      list[dict]
    gaps:      list[dict]
    ego:       dict
    command:   str
    detail:    str
    reasoning: str
    phrase:    str


def resize(frame, width):
    h, w  = frame.shape[:2]
    new_w = (width // 14) * 14
    new_h = int(h * new_w / w)
    new_h = (new_h // 14) * 14
    return cv2.resize(frame, (new_w, new_h))


def process(models: Models, s: Session, frame_bgr: np.ndarray, cfg: Config = CFG) -> FrameResult:
    with s.lock:
        frame_bgr = resize(frame_bgr, cfg.camera.resize_width)

        s.frame_idx += 1
        fi = s.frame_idx

        if s.depth_arr is None or fi % cfg.models.depth_every_n_frames == 0:
            s.depth_arr = models.depth.estimate(frame_bgr)
        depth_arr = s.depth_arr

        boxes = models.detector.track(frame_bgr)
        dets  = agents.measure(boxes, depth_arr, fi, s.track_history, cfg.agents)

        flow = None
        prev = s.prev_frame
        if prev is not None and prev.shape == frame_bgr.shape:
            flow    = models.flow.compute(prev, frame_bgr)
            signals = ego.extract_signals(flow, cfg.ego)
            s.ego   = ego.derive_ego(signals, depth_arr, s.speed_history, cfg.ego, cfg.camera)
            s.speed_history = (s.speed_history + [s.ego["ego_speed_ms"]])[-3:]
        s.prev_frame = frame_bgr.copy()

        gap_list                   = openings.find(depth_arr, cfg.openings, cfg.camera)
        command, detail, reasoning = decision.decide(dets, gap_list, cfg.agents, cfg.openings)

        return FrameResult(
            frame_bgr, depth_arr, flow, dets, gap_list, s.ego,
            command, detail, reasoning, decision.phrase(command),
        )
