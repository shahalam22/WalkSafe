import logging

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
    log.info("Device: %s", device)
    models = Models(
        depth    = DepthPro(cfg.depth_model_id, device),
        flow     = RaftSmall(device),
        detector = YoloTracker(cfg),
    )
    log.info("All models loaded")
    return models
