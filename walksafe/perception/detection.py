import logging

import numpy as np
from ultralytics import YOLO

from walksafe.perception import Box

log = logging.getLogger(__name__)


class YoloTracker:
    def __init__(self, weights: str, conf: float):
        log.info("Loading YOLO (%s)", weights)
        self.model = YOLO(weights)
        self.conf  = conf

    def track(self, frame_bgr: np.ndarray) -> list[Box]:
        try:
            results = self.model.track(
                frame_bgr, conf=self.conf,
                verbose=False, persist=True, tracker="bytetrack.yaml")[0]
        except Exception:
            results = self.model.predict(frame_bgr, conf=self.conf, verbose=False)[0]

        boxes = []
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            tid = int(box.id[0]) if box.id is not None else -1
            boxes.append(Box(x1, y1, x2, y2, int(box.cls[0]), float(box.conf[0]), tid))
        return boxes
