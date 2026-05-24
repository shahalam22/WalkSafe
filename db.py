import sqlite3
import queue
import threading
import time
import uuid

DB_PATH       = "walksafe.db"
BATCH_SIZE    = 50    # flush after N frames
FLUSH_EVERY_S = 5.0   # or after N seconds, whichever comes first

_queue      = queue.Queue()
_session_id = None
_thread     = None


# ── Public API ────────────────────────────────────────────────────────────────

def init():
    global _session_id, _thread
    _create_tables()
    _session_id = str(uuid.uuid4())
    _thread = threading.Thread(target=_worker, daemon=True)
    _thread.start()
    print(f"✅ DB ready   session={_session_id[:8]}   path={DB_PATH}")


def enqueue(frame_idx, command, detail, reasoning, ego, gap_list, dets):
    """Non-blocking. Drops silently if queue is full (never blocks the pipeline)."""
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


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT    PRIMARY KEY,
    started_at   REAL    NOT NULL,
    ended_at     REAL,
    total_frames INTEGER DEFAULT 0
);

-- One row per processed frame. Core record for both medical and robotics research.
CREATE TABLE IF NOT EXISTS frames (
    session_id          TEXT    NOT NULL,
    frame_idx           INTEGER NOT NULL,
    ts                  REAL    NOT NULL,   -- Unix timestamp (seconds)

    -- Navigation decision
    command             TEXT,               -- stop / walk_forward / step_left / …
    detail              TEXT,
    reasoning           TEXT,

    -- Ego motion (medical: gait; robotics: egocentric motion estimation)
    action              TEXT,               -- walking_forward / turning_left / standing_still / …
    action_confidence   REAL,
    ego_speed_ms        REAL,               -- m/s
    speed_trend_ms      REAL,               -- change from previous frame (m/s)
    lateral_drift       TEXT,               -- straight / slight_left / strong_right / …
    flow_lateral_ratio  REAL,               -- 0–1, lateral energy fraction
    flow_rotation_score REAL,               -- 0–1, symmetry score

    -- Scene summary (fast aggregates for dashboard)
    num_agents          INTEGER,
    num_critical        INTEGER,            -- agents with risk_level = critical
    num_gaps            INTEGER,
    best_gap_width_m    REAL,
    best_gap_dist_m     REAL,
    best_gap_direction  TEXT,

    PRIMARY KEY (session_id, frame_idx)
);

-- One row per detected agent per frame. Social navigation / pedestrian trajectory research.
CREATE TABLE IF NOT EXISTS agents (
    session_id        TEXT    NOT NULL,
    frame_idx         INTEGER NOT NULL,
    ts                REAL    NOT NULL,
    track_id          INTEGER,              -- -1 if untracked
    name              TEXT,                 -- person / bicycle / car / …
    conf              REAL,                 -- detection confidence 0–1
    dist_m            REAL,                 -- distance in metres
    dist_m_sigma      REAL,                 -- depth uncertainty (-1 = invalid)
    approach_speed_ms REAL,                 -- negative = approaching
    ttc_s             REAL,                 -- time-to-collision (NULL if not applicable)
    risk_level        TEXT,                 -- critical / high / moderate / low
    motion            TEXT,                 -- approaching / crossing-L / static / …
    track_age         INTEGER,              -- frames this track has been alive
    cx                INTEGER,              -- centre x pixel
    cy                INTEGER               -- centre y pixel
);

-- One row per walkable corridor per frame. Space affordance / navigation planning research.
CREATE TABLE IF NOT EXISTS gaps (
    session_id  TEXT    NOT NULL,
    frame_idx   INTEGER NOT NULL,
    ts          REAL    NOT NULL,
    direction   TEXT,                       -- ahead / left / right
    width_m     REAL,
    dist_m      REAL,
    cx_px       INTEGER,
    width_px    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_frames_session  ON frames (session_id);
CREATE INDEX IF NOT EXISTS idx_frames_ts       ON frames (ts);
CREATE INDEX IF NOT EXISTS idx_agents_session  ON agents (session_id, frame_idx);
CREATE INDEX IF NOT EXISTS idx_agents_track    ON agents (session_id, track_id);
CREATE INDEX IF NOT EXISTS idx_gaps_session    ON gaps   (session_id, frame_idx);
"""


def _create_tables():
    con = sqlite3.connect(DB_PATH)
    con.executescript(_SCHEMA)
    con.commit()
    con.close()


# ── Background writer ─────────────────────────────────────────────────────────

def _worker():
    global _session_id
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous  = NORMAL")

    con.execute("INSERT INTO sessions(session_id, started_at) VALUES (?, ?)",
                (_session_id, time.time()))
    con.commit()

    batch      = []
    last_flush = time.time()

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
                batch      = []
                last_flush = now

        except queue.Empty:
            if batch:
                _flush(con, batch, _session_id)
                batch      = []
                last_flush = time.time()
        except Exception as e:
            print(f"⚠️  DB write error: {e}")


def _close_session(con, session_id, ended_at):
    con.execute(
        "UPDATE sessions SET ended_at=?, total_frames="
        "(SELECT COUNT(*) FROM frames WHERE session_id=?) WHERE session_id=?",
        (ended_at, session_id, session_id)
    )
    con.commit()


def _flush(con, batch, session_id):
    if not batch:
        return

    frame_rows = []
    agent_rows = []
    gap_rows   = []

    for item in batch:
        ego    = item["ego"]   or {}
        gaps   = item["gaps"]  or []
        agents = item["agents"] or []
        ts     = item["ts"]
        fi     = item["frame_idx"]

        best   = max(gaps, key=lambda g: g["width_m"]) if gaps else None
        n_crit = sum(1 for a in agents if a.get("risk_level") == "critical")

        frame_rows.append((
            session_id, fi, ts,
            item["command"], item["detail"], item["reasoning"],
            ego.get("action"),            ego.get("action_confidence"),
            ego.get("ego_speed_ms"),      ego.get("speed_trend_ms"),
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
