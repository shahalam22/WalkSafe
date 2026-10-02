import logging
import time

import numpy as np

from walksafe.config import CFG, ModelConfig
from walksafe.perception import Models

log = logging.getLogger(__name__)


def load(cfg: ModelConfig = CFG.models) -> Models:
    # Imported here so the rest of the package (and the tests) never needs torch.
    import torch

    from walksafe.perception.depth import DepthPro
    from walksafe.perception.detection import YoloTracker
    from walksafe.perception.flow import RaftSmall

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.backends.cudnn.benchmark = True      # every frame has the same size
    log.info("Device: %s", device)
    models = Models(
        depth    = DepthPro(cfg.depth_model_id, device, cfg.depth_fp16),
        flow     = RaftSmall(device, cfg.flow_scale),
        detector = YoloTracker(cfg),
    )
    log.info("All models loaded")
    warm_up(models)
    return models


def warm_up(models: Models, height: int = 378, width: int = 518) -> dict[str, float]:
    """Run each model once, so the first real request is not slowed by GPU start-up."""
    frame = np.random.default_rng(0).integers(0, 255, (height, width, 3), dtype=np.uint8)
    steps = {
        "depth":     lambda: models.depth.estimate(frame),
        "detection": lambda: models.detector.track(frame, models.detector.new_tracker()),
        "flow":      lambda: models.flow.compute(frame, frame),
    }
    timings = {}
    for name, run in steps.items():
        for attempt in ("first", "warm"):
            start = time.perf_counter()
            run()
            timings[f"{name}_{attempt}_ms"] = round((time.perf_counter() - start) * 1000)
    log.info("Warm-up timings: %s", timings)
    return timings
