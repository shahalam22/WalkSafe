import sqlite3

DB_PATH = "walksafe.db"

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT    PRIMARY KEY,
    started_at   REAL    NOT NULL,
    ended_at     REAL,
    total_frames INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS frames (
    session_id          TEXT    NOT NULL,
    frame_idx           INTEGER NOT NULL,
    ts                  REAL    NOT NULL,
    command             TEXT,
    detail              TEXT,
    reasoning           TEXT,
    action              TEXT,
    action_confidence   REAL,
    ego_speed_ms        REAL,
    speed_trend_ms      REAL,
    lateral_drift       TEXT,
    flow_lateral_ratio  REAL,
    flow_rotation_score REAL,
    num_agents          INTEGER,
    num_critical        INTEGER,
    num_gaps            INTEGER,
    best_gap_width_m    REAL,
    best_gap_dist_m     REAL,
    best_gap_direction  TEXT,
    PRIMARY KEY (session_id, frame_idx)
);

CREATE TABLE IF NOT EXISTS agents (
    session_id        TEXT    NOT NULL,
    frame_idx         INTEGER NOT NULL,
    ts                REAL    NOT NULL,
    track_id          INTEGER,
    name              TEXT,
    conf              REAL,
    dist_m            REAL,
    dist_m_sigma      REAL,
    approach_speed_ms REAL,
    ttc_s             REAL,
    risk_level        TEXT,
    motion            TEXT,
    track_age         INTEGER,
    cx                INTEGER,
    cy                INTEGER
);

CREATE TABLE IF NOT EXISTS gaps (
    session_id  TEXT    NOT NULL,
    frame_idx   INTEGER NOT NULL,
    ts          REAL    NOT NULL,
    direction   TEXT,
    width_m     REAL,
    dist_m      REAL,
    cx_px       INTEGER,
    width_px    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_frames_session ON frames (session_id);
CREATE INDEX IF NOT EXISTS idx_frames_ts      ON frames (ts);
CREATE INDEX IF NOT EXISTS idx_agents_session ON agents (session_id, frame_idx);
CREATE INDEX IF NOT EXISTS idx_agents_track   ON agents (session_id, track_id);
CREATE INDEX IF NOT EXISTS idx_gaps_session   ON gaps   (session_id, frame_idx);
"""


def create_tables():
    con = sqlite3.connect(DB_PATH)
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
