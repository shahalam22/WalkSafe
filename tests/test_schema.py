import sqlite3

from walksafe.storage.schema import MIGRATIONS, migrate

PROTOTYPE = """
CREATE TABLE sessions (session_id TEXT PRIMARY KEY, started_at REAL NOT NULL, ended_at REAL, total_frames INTEGER);
CREATE TABLE frames (session_id TEXT, frame_idx INTEGER, ts REAL, command TEXT, detail TEXT, reasoning TEXT,
    action TEXT, action_confidence REAL, ego_speed_ms REAL, speed_trend_ms REAL, lateral_drift TEXT,
    flow_lateral_ratio REAL, flow_rotation_score REAL, num_agents INTEGER, num_critical INTEGER, num_gaps INTEGER,
    best_gap_width_m REAL, best_gap_dist_m REAL, best_gap_direction TEXT, PRIMARY KEY (session_id, frame_idx));
CREATE TABLE agents (session_id TEXT, frame_idx INTEGER, ts REAL, track_id INTEGER, name TEXT, conf REAL,
    dist_m REAL, dist_m_sigma REAL, approach_speed_ms REAL, ttc_s REAL, risk_level TEXT, motion TEXT,
    track_age INTEGER, cx INTEGER, cy INTEGER);
CREATE TABLE gaps (session_id TEXT, frame_idx INTEGER, ts REAL, direction TEXT, width_m REAL, dist_m REAL,
    cx_px INTEGER, width_px INTEGER);
INSERT INTO sessions VALUES ('old', 100.0, 160.0, 1);
INSERT INTO frames VALUES ('old', 1, 101.0, 'step_right', 'd', 'gap_right:1.2m', 'walking_forward', 0.9, 1.1,
    0, 'straight', 0, 0, 1, 0, 2, 1.2, 3.0, 'right');
INSERT INTO agents VALUES ('old', 1, 101.0, 7, 'person', 0.9, 4.0, 0.1, 0.5, 8.0, 'low', 'approaching', 4, 1, 1);
INSERT INTO gaps VALUES ('old', 1, 101.0, 'right', 1.2, 3.0, 400, 80);
INSERT INTO gaps VALUES ('old', 1, 101.0, 'left', 0.7, 2.0, 100, 50);
"""


def tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_new_database_gets_the_srs_schema_and_its_version(tmp_path):
    db = str(tmp_path / "w.db")
    assert migrate(db) == len(MIGRATIONS)
    con = sqlite3.connect(db)
    assert {"user", "session", "decision", "agent", "opening", "event", "schema_version"} <= tables(con)
    assert con.execute("SELECT version FROM schema_version").fetchall() == [(1,)]
    assert migrate(db) == 1                     # running again changes nothing


def test_prototype_database_is_carried_over(tmp_path):
    db = str(tmp_path / "old.db")
    sqlite3.connect(db).executescript(PROTOTYPE)
    migrate(db)
    con = sqlite3.connect(db)
    assert not {"sessions", "frames", "agents", "gaps"} & tables(con)
    assert con.execute("SELECT command, reason, user_speed_ms FROM decision").fetchall() == \
           [("step_right", "gap_right:1.2m", 1.1)]
    assert con.execute("SELECT type, motion FROM agent").fetchall() == [("person", "approaching")]
    assert con.execute("SELECT direction, chosen FROM opening ORDER BY direction").fetchall() == \
           [("left", 0), ("right", 1)]


def test_no_column_can_hold_an_image(tmp_path):
    db = str(tmp_path / "w.db")
    migrate(db)
    con = sqlite3.connect(db)
    types = {row[2].upper() for t in tables(con) for row in con.execute(f"PRAGMA table_info({t})")}
    assert types <= {"TEXT", "REAL", "INTEGER"}
