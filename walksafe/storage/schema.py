"""The session store, as in SRS §4: measurements and decisions only, never images.

Each migration moves the database up one version; schema_version records where
it is. Times are epoch seconds; captured_at, spoken_at and event times come from
the phone's clock, the rest from the server's.
"""
import sqlite3

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS user (
    user_id               TEXT PRIMARY KEY,
    phone_model           TEXT,
    verbosity             TEXT,
    speech_rate           REAL,
    consent_send_images   INTEGER,
    camera_fov_deg        REAL,
    mount_height_m        REAL,
    mount_pitch_deg       REAL,
    shoulder_width_m      REAL,
    clearance_margin_m    REAL,
    depth_scale           REAL,
    depth_check_passed    INTEGER,
    direction_test_passed INTEGER,
    created_at            REAL
);

CREATE TABLE IF NOT EXISTS session (
    session_id      TEXT PRIMARY KEY,
    user_id         TEXT REFERENCES user (user_id),
    started_at      REAL NOT NULL,
    ended_at        REAL,
    end_reason      TEXT,
    total_decisions INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS decision (
    session_id    TEXT    NOT NULL REFERENCES session (session_id),
    source        TEXT    NOT NULL,          -- "server" or "phone"
    sequence      INTEGER NOT NULL,
    captured_at   REAL,
    spoken_at     REAL,
    delay_ms      INTEGER,
    command       TEXT,
    detail        TEXT,
    reason        TEXT,
    confidence    REAL,
    level         TEXT,
    spoken        INTEGER,
    user_speed_ms REAL,
    PRIMARY KEY (session_id, source, sequence)
);

CREATE TABLE IF NOT EXISTS agent (
    session_id        TEXT    NOT NULL,
    sequence          INTEGER NOT NULL,
    track_id          INTEGER,
    type              TEXT,
    dist_m            REAL,
    approach_speed_ms REAL,
    ttc_s             REAL,
    risk              TEXT,
    motion            TEXT
);

CREATE TABLE IF NOT EXISTS opening (
    session_id TEXT    NOT NULL,
    sequence   INTEGER NOT NULL,
    direction  TEXT,
    width_m    REAL,
    dist_m     REAL,
    chosen     INTEGER
);

CREATE TABLE IF NOT EXISTS event (
    session_id  TEXT NOT NULL,
    occurred_at REAL,
    type        TEXT,
    cause       TEXT,
    from_level  TEXT,
    to_level    TEXT
);

CREATE INDEX IF NOT EXISTS idx_decision_time ON decision (session_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_agent         ON agent    (session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_opening       ON opening  (session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_event         ON event    (session_id, occurred_at);
"""

# The prototype's tables, carried into the v1 schema and then dropped.
FROM_PROTOTYPE = """
INSERT OR IGNORE INTO session (session_id, started_at, ended_at, end_reason, total_decisions)
    SELECT session_id, started_at, ended_at, 'prototype', total_frames FROM sessions;
INSERT OR IGNORE INTO decision (session_id, source, sequence, captured_at, command, detail, reason, user_speed_ms)
    SELECT session_id, 'server', frame_idx, ts, command, detail, reasoning, ego_speed_ms FROM frames;
INSERT INTO agent (session_id, sequence, track_id, type, dist_m, approach_speed_ms, ttc_s, risk, motion)
    SELECT session_id, frame_idx, track_id, name, dist_m, approach_speed_ms, ttc_s, risk_level, motion FROM agents;
INSERT INTO opening (session_id, sequence, direction, width_m, dist_m, chosen)
    SELECT g.session_id, g.frame_idx, g.direction, g.width_m, g.dist_m,
           g.direction = f.best_gap_direction AND g.width_m = f.best_gap_width_m
    FROM gaps g LEFT JOIN frames f ON f.session_id = g.session_id AND f.frame_idx = g.frame_idx;
DROP TABLE gaps;
DROP TABLE agents;
DROP TABLE frames;
DROP TABLE sessions;
"""


def to_v1(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_V1)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if {"sessions", "frames", "agents", "gaps"} <= tables:
        con.executescript(FROM_PROTOTYPE)


MIGRATIONS = [to_v1]


def version(con: sqlite3.Connection) -> int:
    con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = con.execute("SELECT version FROM schema_version").fetchone()
    return row[0] if row else 0


def migrate(db_path: str) -> int:
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode = WAL")
        current = version(con)
        for target, step in enumerate(MIGRATIONS[current:], start=current + 1):
            step(con)
            con.execute("DELETE FROM schema_version")
            con.execute("INSERT INTO schema_version VALUES (?)", (target,))
            con.commit()
        return len(MIGRATIONS)
    finally:
        con.close()
