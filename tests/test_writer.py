import math

import numpy as np

from storage.writer import LogWriter, rows


def result(fi, **over):
    r = {
        "frame_idx": fi, "command": "walk_forward", "detail": "1.5m gap", "reasoning": "gap_ahead",
        "ego": {"action": "walking_forward", "action_confidence": np.float32(0.88),
                "ego_speed_ms": np.float64(1.2), "speed_trend_ms": float("nan"),
                "lateral_drift": "straight", "flow_lateral_ratio": 0.1, "flow_rotation_score": 0.2},
        "gaps": [{"direction": "ahead", "width_m": 1.5, "dist_m": 2.0, "cx_px": np.int64(250), "width_px": 120},
                 {"direction": "left", "width_m": 0.8, "dist_m": 3.0, "cx_px": 60, "width_px": 70}],
        "agents": [{"tid": 3, "name": "person", "conf": 0.9, "dist_m": 0.8, "dist_m_sigma": 0.1,
                    "approach_speed_ms": 0.5, "ttc_s": None, "risk_level": "critical", "motion": "approaching",
                    "track_age": 5, "cx": 100, "cy": 200}],
    }
    r.update(over)
    return r


def test_rows_are_plain_json_values():
    frames, agents, gaps = rows([{"session_id": "s1", "ts": 0.0, "result": result(1)}])
    f = frames[0]
    assert f["ts"].startswith("1970-01-01T00:00:00")
    assert type(f["action_confidence"]) is float and math.isclose(f["action_confidence"], 0.88, rel_tol=1e-6)
    assert f["speed_trend_ms"] is None                     # NaN is not valid JSON
    assert f["best_gap_width_m"] == 1.5 and f["best_gap_direction"] == "ahead"
    assert f["num_agents"] == 1 and f["num_critical"] == 1 and f["num_gaps"] == 2
    assert agents[0]["track_id"] == 3 and agents[0]["ttc_s"] is None
    assert type(gaps[0]["cx_px"]) is int


def test_rows_without_gaps_or_agents():
    frames, agents, gaps = rows([{"session_id": "s1", "ts": 1.0, "result": result(2, gaps=[], agents=[])}])
    assert frames[0]["best_gap_width_m"] is None and agents == [] and gaps == []


class FakeDb:
    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times

    def insert(self, table, rows, on_conflict=None):
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("network down")
        if rows:
            self.calls.append(("insert", table, len(rows)))

    def update(self, table, match, values):
        self.calls.append(("update", table, values["end_reason"], values["total_frames"]))


def test_writer_keeps_session_order_and_batches():
    db = FakeDb()
    w = LogWriter(db, batch_size=2, flush_every_s=60, retry_wait_s=0).start()
    w.start_session("s1", "u1", 0.0)
    for i in range(1, 4):
        w.frame("s1", float(i), result(i))
    w.end_session("s1", 5.0, 3, "user")
    w.stop()
    assert db.calls[0] == ("insert", "sessions", 1)
    assert db.calls[1:4] == [("insert", "frames", 2), ("insert", "agents", 2), ("insert", "gaps", 4)]
    assert db.calls[4:7] == [("insert", "frames", 1), ("insert", "agents", 1), ("insert", "gaps", 2)]
    assert db.calls[-1] == ("update", "sessions", "user", 3)


def test_writer_retries_then_succeeds():
    db = FakeDb(fail_times=2)
    w = LogWriter(db, retry_wait_s=0).start()
    w.start_session("s1", "u1", 0.0)
    w.stop()
    assert db.calls == [("insert", "sessions", 1)] and w.dropped == 0
