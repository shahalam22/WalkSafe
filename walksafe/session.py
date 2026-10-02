import threading
from dataclasses import dataclass, field

import numpy as np

from walksafe.config import CFG, Profile
from walksafe.interpretation.agents import Tracks
from walksafe.interpretation.ego import STILL, Ego


@dataclass
class Session:
    """Everything the pipeline remembers between frames for one user."""
    tracker:       object                       # from Detector.new_tracker(); never shared
    profile:       Profile           = CFG.profile
    tracks:        Tracks            = field(default_factory=dict)
    prev_frame:    np.ndarray | None = None
    prev_ts:       float             = 0.0
    depth_arr:     np.ndarray | None = None
    depth_ts:      float             = 0.0
    ego:           Ego               = STILL
    speed_history: list[float]       = field(default_factory=list)
    frame_idx:     int               = 0
    lock:          threading.Lock    = field(default_factory=threading.Lock)
