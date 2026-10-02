import pytest
from test_writer import PROFILE, result

from walksafe.server import EventIn
from walksafe.storage import LogWriter, queries


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "w.db")
    w = LogWriter(path, clock=lambda: 1_010.0)
    w.start_session("s1", PROFILE)
    for seq, delay in ((1, 400), (2, 1500)):
        w.decision("s1", seq, result(seq_ts=1_000.0 + seq))
        w.events("s1", [EventIn(type="delivery", seq=seq, outcome="spoken",
                                spoken_at=(1_000.0 + seq) * 1000 + delay)])
    w.events("s1", [
        EventIn(type="level_change", occurred_at=1_000_000.0, from_level=None, to_level="L0", cause="recovered"),
        EventIn(type="level_change", occurred_at=1_004_000.0, from_level="L0", to_level="L2", cause="server"),
    ])
    w.end_session("s1", "user")
    w.close()
    return path


def test_sessions_and_summary(db):
    s = queries.sessions(db)
    assert list(s["session_id"]) == ["s1"] and list(s["end_reason"]) == ["user"]
    summary = queries.summary(db, "s1", 1200)
    assert summary["decisions"] == 2 and summary["agents"] == 1
    assert summary["on_time_pct"] == 50.0


def test_guidance_delay_and_time_at_each_level(db):
    assert sorted(queries.delays(db, "s1")["delay_ms"]) == [400, 1500]
    levels = dict(zip(*queries.level_time(db, "s1").values.T, strict=True))
    assert levels == {"L0": 4.0, "L2": 6.0}            # session ended at 1010 s


def test_drill_down_from_a_decision_to_its_agents_and_openings(db):
    listing = queries.decision_list(db, "s1")
    assert list(listing["sequence"]) == [1, 2]
    row, agents, openings = queries.decision_detail(db, "s1", "server", 1)
    assert row["reason"].startswith("R")
    assert list(agents["type"]) == ["person"]
    assert openings["chosen"].sum() == 1


def test_dashboard_builds(db):
    from walksafe.ui.dashboard import build_dashboard
    assert build_dashboard(db) is not None
