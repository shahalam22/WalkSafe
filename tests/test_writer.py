import sqlite3

import numpy as np
from conftest import fake_models

from walksafe import pipeline
from walksafe.interpretation.openings import best_opening
from walksafe.session import Session
from walksafe.storage import schema, writer


def drain():
    items = []
    while not writer._queue.empty():
        items.append(writer._queue.get_nowait())
    return items


def test_logged_best_opening_is_the_one_the_decision_used(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    schema.create_tables()
    m = fake_models()
    r = pipeline.process(m, Session(m.detector.new_tracker()),
                         np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8), 0.0)
    drain()
    writer.enqueue(1, r)
    con = sqlite3.connect(schema.DB_PATH)
    writer._flush(con, drain(), "s1")
    best = best_opening(r.openings)
    row  = con.execute("SELECT command, reasoning, best_gap_width_m, best_gap_direction FROM frames").fetchone()
    assert row == (r.decision.command, r.decision.reason, best.width_m, best.direction)


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
