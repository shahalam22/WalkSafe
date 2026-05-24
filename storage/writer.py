import sqlite3
import queue
import threading
import time
import uuid

from .schema import DB_PATH, create_tables

BATCH_SIZE    = 50
FLUSH_EVERY_S = 5.0

_queue      = queue.Queue()
_session_id = None
_thread     = None


def init():
    global _session_id, _thread
    create_tables()
    _session_id = str(uuid.uuid4())
    _thread = threading.Thread(target=_worker, daemon=True)
    _thread.start()
    print(f"✅ DB ready   session={_session_id[:8]}   path={DB_PATH}")


def enqueue(frame_idx, command, detail, reasoning, ego, gap_list, dets):
    """Non-blocking. Drops silently if queue is full — never blocks the pipeline."""
    try:
        _queue.put_nowait({
            "frame_idx": frame_idx,
            "ts":        time.time(),
            "command":   command,
            "detail":    detail,
            "reasoning": reasoning,
            "ego":       ego,
            "gaps":      gap_list,
            "agents":    dets,
        })
    except queue.Full:
        pass


def new_session():
    """Call on reset — closes current session and starts a fresh one."""
    _queue.put_nowait({"_new_session": True, "ts": time.time()})


# ── Internal ───────────────────────────────���──────────────────────────────────

def _worker():
    global _session_id
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous  = NORMAL")
    con.execute("INSERT INTO sessions(session_id, started_at) VALUES (?, ?)",
                (_session_id, time.time()))
    con.commit()

    batch, last_flush = [], time.time()

    while True:
        try:
            item = _queue.get(timeout=1.0)

            if item.get("_new_session"):
                _flush(con, batch, _session_id)
                batch = []
                _close_session(con, _session_id, item["ts"])
                _session_id = str(uuid.uuid4())
                con.execute("INSERT INTO sessions(session_id, started_at) VALUES (?, ?)",
                            (_session_id, item["ts"]))
                con.commit()
                last_flush = time.time()
                continue

            batch.append(item)
            now = time.time()
            if len(batch) >= BATCH_SIZE or (now - last_flush) >= FLUSH_EVERY_S:
                _flush(con, batch, _session_id)
                batch, last_flush = [], now

        except queue.Empty:
            if batch:
                _flush(con, batch, _session_id)
                batch, last_flush = [], time.time()
        except Exception as e:
            print(f"⚠️  DB write error: {e}")


def _close_session(con, session_id, ended_at):
    con.execute(
        "UPDATE sessions SET ended_at=?, total_frames="
        "(SELECT COUNT(*) FROM frames WHERE session_id=?) WHERE session_id=?",
        (ended_at, session_id, session_id),
    )
    con.commit()


def _flush(con, batch, session_id):
    if not batch:
        return

    frame_rows, agent_rows, gap_rows = [], [], []

    for item in batch:
        ego    = item["ego"]    or {}
        gaps   = item["gaps"]   or []
        agents = item["agents"] or []
        ts, fi = item["ts"], item["frame_idx"]

        best   = max(gaps, key=lambda g: g["width_m"]) if gaps else None
        n_crit = sum(1 for a in agents if a.get("risk_level") == "critical")

        frame_rows.append((
            session_id, fi, ts,
            item["command"], item["detail"], item["reasoning"],
            ego.get("action"),             ego.get("action_confidence"),
            ego.get("ego_speed_ms"),       ego.get("speed_trend_ms"),
            ego.get("lateral_drift"),
            ego.get("flow_lateral_ratio"), ego.get("flow_rotation_score"),
            len(agents), n_crit, len(gaps),
            best["width_m"]   if best else None,
            best["dist_m"]    if best else None,
            best["direction"] if best else None,
        ))

        for a in agents:
            agent_rows.append((
                session_id, fi, ts,
                a.get("tid"),  a.get("name"),  a.get("conf"),
                a.get("dist_m"), a.get("dist_m_sigma"),
                a.get("approach_speed_ms"), a.get("ttc_s"),
                a.get("risk_level"), a.get("motion"),
                a.get("track_age"), a.get("cx"), a.get("cy"),
            ))

        for g in gaps:
            gap_rows.append((
                session_id, fi, ts,
                g.get("direction"), g.get("width_m"), g.get("dist_m"),
                g.get("cx_px"), g.get("width_px"),
            ))

    con.executemany(
        "INSERT OR IGNORE INTO frames VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        frame_rows,
    )
    if agent_rows:
        con.executemany(
            "INSERT INTO agents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            agent_rows,
        )
    if gap_rows:
        con.executemany(
            "INSERT INTO gaps VALUES (?,?,?,?,?,?,?,?)",
            gap_rows,
        )
    con.commit()
