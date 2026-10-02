import logging

import numpy as np
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import IterableSimpleNamespace

from walksafe.config import ModelConfig
from walksafe.perception import Box

log = logging.getLogger(__name__)


class YoloTracker:
    def __init__(self, cfg: ModelConfig):
        log.info("Loading YOLO (%s)", cfg.yolo_model)
        self.model = YOLO(cfg.yolo_model)
        self.cfg   = cfg

    def new_tracker(self) -> BYTETracker:
        c = self.cfg
        return BYTETracker(IterableSimpleNamespace(
            tracker_type="bytetrack", track_high_thresh=c.track_high_thresh,
            track_low_thresh=c.track_low_thresh, new_track_thresh=c.new_track_thresh,
            track_buffer=c.track_buffer, match_thresh=c.match_thresh, fuse_score=True))

    def track(self, frame_bgr: np.ndarray, tracker: BYTETracker) -> list[Box]:
        result = self.model.predict(frame_bgr, conf=self.cfg.yolo_conf,
                                    classes=list(self.cfg.agent_classes), verbose=False)[0]
        det    = result.boxes.cpu().numpy()
        boxes, tracked = [], set()
        for x1, y1, x2, y2, tid, score, cls, idx in tracker.update(det, frame_bgr):
            tracked.add(int(idx))
            boxes.append(Box(int(x1), int(y1), int(x2), int(y2), int(cls), float(score), int(tid)))
        for i in range(len(det)):
            if i not in tracked:
                x1, y1, x2, y2 = map(int, det.xyxy[i])
                boxes.append(Box(x1, y1, x2, y2, int(det.cls[i]), float(det.conf[i]), -1))
        return boxes
