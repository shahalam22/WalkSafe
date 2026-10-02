"""Writes sessions, decisions and events in the background (FR-24, FR-25).

Callers only put items on a bounded queue, which never blocks: when it is
full, the item is dropped and counted. One thread writes them in batches.
"""
import atexit
import logging
import queue
import sqlite3
import threading
import time

from walksafe.config import CFG, StorageConfig
from walksafe.interpretation.openings import best_opening

from .schema import migrate

log = logging.getLogger(__name__)

_STOP = object()


class LogWriter:
    def __init__(self, db_path: str, cfg: StorageConfig = CFG.storage, clock=time.time):
        migrate(db_path)
        self.db_path  = db_path
        self.cfg      = cfg
        self.clock    = clock
        self.dropped  = 0
        self._queue   = queue.Queue(maxsize=cfg.queue_size)
        self._open    = set()
        self._lock    = threading.Lock()
        self._thread  = threading.Thread(target=self._run, name="log-writer", daemon=True)
        self._thread.start()
        atexit.register(self.close)

    # Called from request threads

    def start_session(self, session_id: str, profile: dict) -> None:
        with self._lock:
            self._open.add(session_id)
        self._put("user", {**profile, "created_at": self.clock()})
        self._put("session", (session_id, profile.get("user_id"), self.clock()))

    def end_session(self, session_id: str, reason: str) -> None:
        with self._lock:
            if session_id not in self._open:
                return
            self._open.discard(session_id)
        self._put("end", (self.clock(), reason, session_id, session_id))

    def decision(self, session_id: str, seq: int, r) -> None:
        """r is a pipeline.FrameResult."""
        d, best = r.decision, best_opening(r.openings)
        self._put("decision", (
            (session_id, "server", seq, r.capture_ts, d.command, d.detail, d.reason,
             d.confidence, r.level, r.ego.speed_ms),
            [(session_id, seq, a.tid, a.kind, a.dist_m, a.approach_speed_ms, a.ttc_s, a.risk, a.motion)
             for a in r.agents],
            [(session_id, seq, o.direction, o.width_m, o.dist_m, o is best) for o in r.openings or []],
        ))

    def events(self, session_id: str, events: list) -> None:
        """Events from the phone (server.EventIn); times are in phone milliseconds."""
        for e in events:
            at = None if e.occurred_at is None else e.occurred_at / 1000
            if e.type == "delivery":
                spoken_at = None if e.spoken_at is None else e.spoken_at / 1000
                self._put("delivery", (e.outcome == "spoken", spoken_at, spoken_at, session_id, e.seq))
            elif e.type == "phone_stop":
                self._put("decision", ((session_id, "phone", e.seq, at, "stop", "something close ahead",
                                        f"phone expansion check ttc={e.ttc_s}s", None, None, None), [], []))
                self._put("delivery_phone", (at, session_id, e.seq))
            else:
                self._put("event", (session_id, at, e.type, e.cause, e.from_level, e.to_level))

    def server_event(self, session_id: str, kind: str, cause: str) -> None:
        self._put("event", (session_id, self.clock(), kind, cause, None, None))

    def close(self) -> None:
        """End every open session and write everything still queued."""
        with self._lock:
            still_open, self._open = list(self._open), set()
        for session_id in still_open:
            self._put("end", (self.clock(), "shutdown", session_id, session_id))
        if self._thread.is_alive():
            self._queue.put(_STOP)
            self._thread.join(timeout=self.cfg.close_timeout_s)

    def _put(self, kind: str, item) -> None:
        try:
            self._queue.put_nowait((kind, item))
        except queue.Full:
            with self._lock:
                self.dropped += 1
                if self.dropped % 100 == 1:
                    log.warning("Log queue full; %d items dropped so far", self.dropped)

    # The writer thread

    def _run(self) -> None:
        con = sqlite3.connect(self.db_path, timeout=self.cfg.busy_timeout_s)
        con.execute("PRAGMA synchronous = NORMAL")
        stop = False
        while not stop:
            batch = []
            try:
                batch.append(self._queue.get(timeout=self.cfg.flush_every_s))
                while len(batch) < self.cfg.batch_size:
                    batch.append(self._queue.get_nowait())
            except queue.Empty:
                pass
            stop = any(item is _STOP for item in batch)
            try:
                for kind, item in (b for b in batch if b is not _STOP):
                    _write(con, kind, item)
                con.commit()
            except sqlite3.Error:
                log.exception("Could not write %d log items", len(batch))
                con.rollback()
        con.close()


def _write(con: sqlite3.Connection, kind: str, item) -> None:
    if kind == "user":
        cols    = [c for c in USER_COLUMNS if c in item]
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("user_id", "created_at"))
        con.execute(f"INSERT INTO user ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
                    f"ON CONFLICT (user_id) DO " + (f"UPDATE SET {updates}" if updates else "NOTHING"),
                    [item[c] for c in cols])
    elif kind == "session":
        con.execute("INSERT OR IGNORE INTO session (session_id, user_id, started_at) VALUES (?, ?, ?)", item)
    elif kind == "end":
        con.execute("UPDATE session SET ended_at = ?, end_reason = ?, total_decisions = "
                    "(SELECT COUNT(*) FROM decision WHERE session_id = ?) WHERE session_id = ?", item)
    elif kind == "decision":
        row, agents, openings = item
        con.execute("INSERT OR IGNORE INTO decision (session_id, source, sequence, captured_at, command, detail, "
                    "reason, confidence, level, user_speed_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
        con.executemany("INSERT INTO agent VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", agents)
        con.executemany("INSERT INTO opening VALUES (?, ?, ?, ?, ?, ?)", openings)
    elif kind == "delivery":
        con.execute("UPDATE decision SET spoken = ?, spoken_at = ?, "
                    "delay_ms = CAST(ROUND((? - captured_at) * 1000) AS INTEGER) "
                    "WHERE session_id = ? AND source = 'server' AND sequence = ?", item)
    elif kind == "delivery_phone":
        con.execute("UPDATE decision SET spoken = 1, spoken_at = ? "
                    "WHERE session_id = ? AND source = 'phone' AND sequence = ?", item)
    elif kind == "event":
        con.execute("INSERT INTO event VALUES (?, ?, ?, ?, ?, ?)", item)


USER_COLUMNS = ("user_id", "phone_model", "verbosity", "speech_rate", "consent_send_images", "camera_fov_deg",
                "mount_height_m", "mount_pitch_deg", "shoulder_width_m", "clearance_margin_m", "depth_scale",
                "depth_check_passed", "direction_test_passed", "created_at")
