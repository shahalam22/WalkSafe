"""Background log writer.

The pipeline hands each frame's result to a queue and returns at once; this
thread sends them to Supabase in batches, so the database never adds latency
to guidance. Session start and end go through the same queue, so they reach
the database in order with the frames.
"""
import math
import queue
import threading
import time
from datetime import datetime, timezone

BATCH_SIZE    = 50
FLUSH_EVERY_S = 5.0
MAX_QUEUE     = 20_000
RETRIES       = 3

_STOP = object()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _num(v):
    """Plain JSON number, or None for missing / NaN / inf."""
    if v is None:
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _int(v):
    return None if v is None else int(v)


class LogWriter:
    def __init__(self, db, batch_size=BATCH_SIZE, flush_every_s=FLUSH_EVERY_S, retry_wait_s=1.0):
        self.db            = db
        self.batch_size    = batch_size
        self.flush_every_s = flush_every_s
        self.retry_wait_s  = retry_wait_s
        self.dropped       = 0
        self._q            = queue.Queue(MAX_QUEUE)
        self._thread       = None

    def start(self):
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout=30):
        """Write what is queued, then end the thread."""
        self._q.put(_STOP)
        if self._thread:
            self._thread.join(timeout)

    # ── Called by the server (never blocks) ───────────────────────────────────

    def start_session(self, session_id, user_id, started_at):
        self._put({"kind": "start", "session_id": session_id,
                   "user_id": user_id, "ts": started_at})

    def frame(self, session_id, ts, result):
        self._put({"kind": "frame", "session_id": session_id, "ts": ts, "result": result})

    def end_session(self, session_id, ended_at, total_frames, reason):
        self._put({"kind": "end", "session_id": session_id, "ts": ended_at,
                   "total_frames": total_frames, "reason": reason})

    def _put(self, item):
        try:
            self._q.put_nowait(item)
        except queue.Full:
            self.dropped += 1

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _worker(self):
        batch, last_flush = [], time.time()
        while True:
            try:
                item = self._q.get(timeout=1.0)
            except queue.Empty:
                item = None

            if item is _STOP:
                self._flush(batch)
                return
            if item is not None and item["kind"] == "frame":
                batch.append(item)
            elif item is not None:                  # start / end: keep the order
                self._flush(batch)
                batch = []
                self._session_event(item)

            if batch and (len(batch) >= self.batch_size
                          or time.time() - last_flush >= self.flush_every_s
                          or item is None):
                self._flush(batch)
                batch = []
            if not batch:
                last_flush = time.time()

    def _session_event(self, item):
        if item["kind"] == "start":
            self._send(self.db.insert, "sessions", [{
                "session_id": item["session_id"],
                "user_id":    item["user_id"],
                "started_at": iso(item["ts"]),
            }])
        else:
            self._send(self.db.update, "sessions", {"session_id": item["session_id"]}, {
                "ended_at":     iso(item["ts"]),
                "total_frames": item["total_frames"],
                "end_reason":   item["reason"],
            })

    def _flush(self, batch):
        if not batch:
            return
        frames, agents, gaps = rows(batch)
        self._send(self.db.insert, "frames", frames, on_conflict="session_id,frame_idx")
        self._send(self.db.insert, "agents", agents)
        self._send(self.db.insert, "gaps",   gaps)

    def _send(self, fn, *args, **kwargs):
        for attempt in range(RETRIES):
            try:
                fn(*args, **kwargs)
                return True
            except Exception as e:
                if attempt == RETRIES - 1:
                    self.dropped += 1
                    print(f"⚠️  DB write failed, dropped ({args[0]}): {e}")
                    return False
                time.sleep(self.retry_wait_s * (attempt + 1))


def rows(batch):
    """Frame results -> rows for the frames, agents and gaps tables."""
    frames, agents, gaps = [], [], []
    for item in batch:
        r   = item["result"]
        sid = item["session_id"]
        fi  = r["frame_idx"]
        ts  = iso(item["ts"])
        ego = r.get("ego")    or {}
        gl  = r.get("gaps")   or []
        al  = r.get("agents") or []

        best   = max(gl, key=lambda g: g["width_m"]) if gl else None
        n_crit = sum(1 for a in al if a.get("risk_level") == "critical")

        frames.append({
            "session_id":          sid,
            "frame_idx":           fi,
            "ts":                  ts,
            "command":             r.get("command"),
            "detail":              r.get("detail"),
            "reasoning":           r.get("reasoning"),
            "action":              ego.get("action"),
            "action_confidence":   _num(ego.get("action_confidence")),
            "ego_speed_ms":        _num(ego.get("ego_speed_ms")),
            "speed_trend_ms":      _num(ego.get("speed_trend_ms")),
            "lateral_drift":       ego.get("lateral_drift"),
            "flow_lateral_ratio":  _num(ego.get("flow_lateral_ratio")),
            "flow_rotation_score": _num(ego.get("flow_rotation_score")),
            "num_agents":          len(al),
            "num_critical":        n_crit,
            "num_gaps":            len(gl),
            "best_gap_width_m":    _num(best["width_m"])  if best else None,
            "best_gap_dist_m":     _num(best["dist_m"])   if best else None,
            "best_gap_direction":  best["direction"]      if best else None,
        })
        for a in al:
            agents.append({
                "session_id":        sid,
                "frame_idx":         fi,
                "ts":                ts,
                "track_id":          _int(a.get("tid")),
                "name":              a.get("name"),
                "conf":              _num(a.get("conf")),
                "dist_m":            _num(a.get("dist_m")),
                "dist_m_sigma":      _num(a.get("dist_m_sigma")),
                "approach_speed_ms": _num(a.get("approach_speed_ms")),
                "ttc_s":             _num(a.get("ttc_s")),
                "risk_level":        a.get("risk_level"),
                "motion":            a.get("motion"),
                "track_age":         _int(a.get("track_age")),
                "cx":                _int(a.get("cx")),
                "cy":                _int(a.get("cy")),
            })
        for g in gl:
            gaps.append({
                "session_id": sid,
                "frame_idx":  fi,
                "ts":         ts,
                "direction":  g.get("direction"),
                "width_m":    _num(g.get("width_m")),
                "dist_m":     _num(g.get("dist_m")),
                "cx_px":      _int(g.get("cx_px")),
                "width_px":   _int(g.get("width_px")),
            })
    return frames, agents, gaps
