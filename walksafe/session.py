import threading
from dataclasses import dataclass, field

import numpy as np

from walksafe.interpretation.ego import standing_still


@dataclass
class Session:
    """Everything the pipeline remembers between frames for one user."""
    prev_frame:    np.ndarray | None = None
    depth_arr:     np.ndarray | None = None
    speed_history: list[float]       = field(default_factory=list)
    frame_idx:     int               = 0
    ego:           dict              = field(default_factory=standing_still)
    track_history: dict              = field(default_factory=dict)
    lock:          threading.Lock    = field(default_factory=threading.Lock)
