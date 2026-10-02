import sqlite3

from walksafe.storage import schema, writer


def test_flush_writes_frame_agent_and_gap_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    schema.create_tables()
    con = sqlite3.connect(schema.DB_PATH)
    item = {
        "frame_idx": 1, "ts": 100.0, "command": "walk_forward", "detail": "d", "reasoning": "r",
        "ego": {"action": "walking_forward", "ego_speed_ms": 1.1},
        "gaps": [{"direction": "ahead", "width_m": 1.5, "dist_m": 4.0, "cx_px": 259, "width_px": 150}],
        "agents": [{"tid": 3, "name": "person", "risk_level": "low", "dist_m": 5.0}],
    }
    writer._flush(con, [item], "s1")
    assert con.execute("SELECT command, best_gap_width_m FROM frames").fetchall() == [("walk_forward", 1.5)]
    assert con.execute("SELECT track_id, name FROM agents").fetchall() == [(3, "person")]
    assert con.execute("SELECT COUNT(*) FROM gaps").fetchone()[0] == 1


def test_log_queue_has_no_size_limit():
    # Characterises defect 10, fixed in Phase 8.
    assert writer._queue.maxsize == 0


def test_schema_has_no_image_columns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    schema.create_tables()
    con   = sqlite3.connect(schema.DB_PATH)
    types = {row[2].upper() for t in ("sessions", "frames", "agents", "gaps")
             for row in con.execute(f"PRAGMA table_info({t})")}
    assert "BLOB" not in types
