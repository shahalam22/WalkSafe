import threading
import uuid
from concurrent.futures import Future
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
    depth_job:     Future | None     = None     # a depth map being computed in the background
    ego:           Ego               = STILL
    speed_history: list[float]       = field(default_factory=list)
    frame_idx:     int               = 0
    # Re-entrant so the server can test "busy" with a non-blocking acquire
    # and then run the pipeline, which takes the lock again.
    lock:          threading.RLock   = field(default_factory=threading.RLock)
    # Server bookkeeping
    session_id:    str               = field(default_factory=lambda: uuid.uuid4().hex)
    purpose:       str               = "walk"
    last_seq:      int               = -1
    last_seen:     float             = 0.0
    panel:         bytes | None      = None     # latest diagnostic JPEG, in memory only


class SessionStore:
    """Live sessions by id; sessions idle for too long are dropped."""

    def __init__(self, idle_s: float = CFG.server.session_idle_s):
        self.idle_s    = idle_s
        self._sessions: dict[str, Session] = {}
        self._lock     = threading.Lock()

    def add(self, s: Session) -> Session:
        with self._lock:
            self._sessions[s.session_id] = s
        return s

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def remove(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.pop(session_id, None)

    def expire(self, now: float) -> list[Session]:
        with self._lock:
            idle = [s for s in self._sessions.values() if now - s.last_seen > self.idle_s]
            for s in idle:
                del self._sessions[s.session_id]
        return idle

    def all(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def __len__(self) -> int:
        return len(self._sessions)
