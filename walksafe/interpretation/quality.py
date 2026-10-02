"""Whether a frame is usable (FR-1) and how far its result can be trusted (FR-10)."""
from dataclasses import dataclass

import cv2
import numpy as np

from walksafe.config import CFG, AgentConfig, QualityConfig


@dataclass(frozen=True)
class FrameQuality:
    ok:         bool
    cause:      str          # "", "dark", "bright" or "blur"
    brightness: float
    sharpness:  float


def check_frame(frame_bgr: np.ndarray, cfg: QualityConfig = CFG.quality) -> FrameQuality:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    small = cv2.resize(gray, (cfg.blur_width_px, max(1, h * cfg.blur_width_px // w)))
    brightness = float(gray.mean())
    sharpness  = float(cv2.Laplacian(small, cv2.CV_64F).var())

    cause = ""
    if brightness < cfg.dark_max:
        cause = "dark"
    elif brightness > cfg.bright_min:
        cause = "bright"
    elif sharpness < cfg.blur_min:
        cause = "blur"
    return FrameQuality(cause == "", cause, round(brightness, 1), round(sharpness, 1))


def confidence(agents, cfg: QualityConfig = CFG.quality, agent_cfg: AgentConfig = CFG.agents) -> tuple[float, str]:
    """Lowest trust over the agents that matter, with the reason for it."""
    score, cause = 1.0, ""
    for a in agents:
        if a.dist_sigma > cfg.depth_sigma_moderate:
            s, why = cfg.poor_depth_score, f"unsteady depth on {a.kind}"
        elif a.dist_sigma > cfg.depth_sigma_reliable:
            s, why = cfg.moderate_depth_score, f"unsteady depth on {a.kind}"
        elif a.motion == "new" and a.dist_m < agent_cfg.close_distance_m:
            s, why = cfg.new_track_score, f"{a.kind} not yet tracked"
        else:
            continue
        if s < score:
            score, cause = s, why
    return score, cause
