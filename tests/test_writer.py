import sqlite3
import time

import numpy as np
from conftest import FakeDetector, fake_models

from walksafe import pipeline
from walksafe.config import StorageConfig
from walksafe.perception import Box
from walksafe.server import EventIn
from walksafe.session import Session
from walksafe.storage import LogWriter

PROFILE = {"user_id": "u1", "phone_model": "Pixel", "consent_send_images": True, "shoulder_width_m": 0.45,
           "depth_check_passed": True, "direction_test_passed": True}


def result(seq_ts=1_000.0):
    m = fake_models(detector=FakeDetector([Box(200, 150, 260, 350, 0, 0.9, 4)]))
    frame = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    return pipeline.process(m, Session(m.detector.new_tracker()), frame, seq_ts)


def rows(db, sql):
    return sqlite3.connect(db).execute(sql).fetchall()


def test_t13_a_decision_is_stored_with_its_reason_agents_and_openings(tmp_path):
    db = str(tmp_path / "w.db")
    w = LogWriter(db)
    w.start_session("s1", PROFILE)
    r = result()
    w.decision("s1", 1, r)
    w.close()
    assert rows(db, "SELECT command, reason, level FROM decision") == \
           [(r.decision.command, r.decision.reason, r.level)]
    assert rows(db, "SELECT type FROM agent") == [("person",)]
    assert rows(db, "SELECT COUNT(*) FROM opening WHERE chosen = 1") == [(1,)]
    assert rows(db, "SELECT phone_model, shoulder_width_m FROM user") == [("Pixel", 0.45)]


def test_deliveries_phone_stops_and_events_from_the_phone(tmp_path):
    db = str(tmp_path / "w.db")
    w = LogWriter(db)
    w.start_session("s1", PROFILE)
    w.decision("s1", 1, result(seq_ts=1_000.0))
    w.events("s1", [
        EventIn(type="delivery", seq=1, outcome="spoken", spoken_at=1_000_400.0),
        EventIn(type="phone_stop", seq=1, occurred_at=1_002_000.0, ttc_s=1.2),
        EventIn(type="level_change", occurred_at=1_003_000.0, cause="the server is not answering in time",
                from_level="L0", to_level="L2"),
    ])
    w.close()
    assert rows(db, "SELECT spoken, delay_ms FROM decision WHERE source = 'server'") == [(1, 400)]
    assert rows(db, "SELECT command, spoken FROM decision WHERE source = 'phone'") == [("stop", 1)]
    assert rows(db, "SELECT to_level, cause FROM event") == [("L2", "the server is not answering in time")]


def test_t13_sessions_are_closed_on_end_and_at_shutdown(tmp_path):
    db = str(tmp_path / "w.db")
    w = LogWriter(db)
    w.start_session("ended", PROFILE)
    w.start_session("open", PROFILE)
    w.decision("ended", 1, result())
    w.end_session("ended", "user")
    w.close()                                    # also registered with atexit
    assert sorted(rows(db, "SELECT session_id, end_reason, total_decisions FROM session")) == \
           [("ended", "user", 1), ("open", "shutdown", 0)]
    assert rows(db, "SELECT COUNT(*) FROM session WHERE ended_at IS NULL") == [(0,)]


def test_t13_the_writer_never_blocks_guidance_and_counts_what_it_drops(tmp_path):
    db = str(tmp_path / "w.db")
    w = LogWriter(db, StorageConfig(queue_size=5, flush_every_s=0.05, busy_timeout_s=0.2))
    lock = sqlite3.connect(db, isolation_level=None)
    lock.execute("BEGIN EXCLUSIVE")              # the database is stuck
    r = result()
    t0 = time.perf_counter()
    for seq in range(200):
        w.decision("s1", seq, r)
    assert time.perf_counter() - t0 < 0.5
    assert w.dropped > 0
    lock.execute("ROLLBACK")
    w.close()
