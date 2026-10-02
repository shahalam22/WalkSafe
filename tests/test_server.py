import tempfile

import cv2
import numpy as np
import pytest
from conftest import FakeDepth, FakeDetector, fake_models
from fastapi.testclient import TestClient

from walksafe.config import CFG
from walksafe.decision import COMMANDS
from walksafe.server import create_app

PROFILE = {"consent_send_images": True, "depth_check_passed": True, "direction_test_passed": True}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class BrokenDetector(FakeDetector):
    broken = False

    def track(self, frame_bgr, tracker):
        if self.broken:
            raise RuntimeError("CUDA error")
        return []


def jpeg(seed=0):
    img = np.random.default_rng(seed).integers(0, 255, (388, 518, 3), dtype=np.uint8)
    return cv2.imencode(".jpg", img)[1].tobytes()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def client(clock):
    return TestClient(create_app(fake_models(), clock=clock))


def start(client, **profile):
    r = client.post("/api/session", json={"profile": {**PROFILE, **profile}})
    assert r.status_code == 200
    return r.json()["session_id"]


def send(client, sid, seq, ts=None, image=None):
    ts = 1_759_400_000_000.0 + seq * 500 if ts is None else ts
    return client.post("/api/frame", data={"session_id": sid, "seq": seq, "capture_ts": ts},
                       files={"image": ("f.jpg", image if image is not None else jpeg(seq), "image/jpeg")})


def test_frame_returns_one_command_with_its_reason_and_timing(client):
    sid = start(client)
    body = send(client, sid, 1).json()
    assert body["command"] in COMMANDS
    assert body["seq"] == 1 and body["capture_ts"] == 1_759_400_000_500.0
    assert body["reason"] and body["phrase"] and body["level"] in ("L0", "L1")
    assert body["server_ms"] >= 0 and "depth" in body["timings"]


def test_session_needs_consent_to_send_images(client):
    r = client.post("/api/session", json={"profile": {"consent_send_images": False}})
    assert r.status_code == 403 and r.json()["detail"] == "consent_required"


def test_profile_values_are_validated(client):
    r = client.post("/api/session", json={"profile": {**PROFILE, "shoulder_width_m": 3.0}})
    assert r.status_code == 422


def test_out_of_order_frame_is_refused(client):
    sid = start(client)
    assert send(client, sid, 5).status_code == 200
    assert send(client, sid, 4).status_code == 409
    assert send(client, sid, 5).status_code == 409
    assert send(client, sid, 6).status_code == 200


def test_frame_for_a_busy_session_is_refused_not_queued(client):
    sid = start(client)
    s = client.app.state.sessions.get(sid)
    with s.lock:
        # The test client runs the handler on another thread, so the lock is held elsewhere.
        assert send(client, sid, 1).status_code == 429


def test_unknown_or_ended_session(client):
    assert send(client, "nope", 1).status_code == 404
    sid = start(client)
    assert client.post("/api/session/end", json={"session_id": sid}).json() == {"ok": True}
    assert send(client, sid, 1).status_code == 404


def test_bad_and_oversized_images(client):
    sid = start(client)
    assert send(client, sid, 1, image=b"not a jpeg").status_code == 400
    big = b"\xff" * (CFG.server.max_image_bytes + 1)
    assert send(client, sid, 2, image=big).status_code == 413


def test_pipeline_fault_is_reported_and_the_session_survives(clock):
    detector = BrokenDetector()
    client   = TestClient(create_app(fake_models(detector=detector), clock=clock))
    sid = start(client)
    detector.broken = True
    r = send(client, sid, 1)
    assert r.status_code == 500 and r.json() == {"error": "pipeline_fault", "seq": 1}
    detector.broken = False
    assert send(client, sid, 2).status_code == 200


def test_idle_sessions_expire(client, clock):
    sid = start(client)
    clock.now += CFG.server.session_idle_s + 1
    assert send(client, sid, 1).status_code == 404


def test_sessions_do_not_share_state(client):
    a, b = start(client), start(client)
    assert send(client, a, 10).status_code == 200
    assert send(client, b, 1).status_code == 200           # b's sequence is its own
    sessions = client.app.state.sessions
    assert sessions.get(a).tracker is not sessions.get(b).tracker


def test_github_pages_origin_is_allowed(client):
    r = client.options("/api/session", headers={"Origin": "https://shahalam22.github.io",
                                                "Access-Control-Request-Method": "POST"})
    assert r.headers["access-control-allow-origin"] == "https://shahalam22.github.io"
    r = client.options("/api/session", headers={"Origin": "https://evil.example",
                                                "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_no_frame_is_written_to_disk(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    sid = start(client)
    for seq in range(1, 4):
        send(client, sid, seq)
    assert list(tmp_path.rglob("*")) == []


def test_phone_page_and_its_config_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "Start guidance" in page.text
    assert client.get("/js/guidance.js").status_code == 200
    config = client.get("/js/config.js")
    assert config.headers["content-type"].startswith("text/javascript")
    assert '"stale_after_ms": 2000' in config.text


def test_every_setting_the_page_reads_comes_from_config_py():
    import re
    from dataclasses import fields
    from pathlib import Path

    from walksafe.config import PhoneConfig

    web  = Path(__file__).parents[1] / "walksafe" / "web" / "js"
    js   = " ".join(p.read_text() for p in web.glob("*.js"))
    used = set(re.findall(r"\b(?:cfg|CONFIG|this\.cfg)\.([a-z_]+)", js))
    assert used and used <= {f.name for f in fields(PhoneConfig)}


def test_events_are_accepted_for_a_live_session(client):
    sid = start(client)
    batch = {"session_id": sid, "events": [
        {"type": "level_change", "occurred_at": 1.0, "cause": "server not responding",
         "from_level": "L0", "to_level": "L2"},
        {"type": "delivery", "seq": 3, "outcome": "spoken", "spoken_at": 2.0},
        {"type": "phone_stop", "occurred_at": 3.0, "ttc_s": 1.1},
    ]}
    assert client.post("/api/event", json=batch).json() == {"ok": True, "accepted": 3}
    assert client.post("/api/event", json={**batch, "session_id": "nope"}).status_code == 404
    bad = {"session_id": sid, "events": [{"type": "selfie"}]}
    assert client.post("/api/event", json=bad).status_code == 422


def test_walking_needs_setup_to_have_passed(client):
    for flags in ({"depth_check_passed": False}, {"direction_test_passed": False}):
        r = client.post("/api/session", json={"profile": {**PROFILE, **flags}})
        assert r.status_code == 403 and r.json()["detail"] == "setup_incomplete"
    setup = client.post("/api/session", json={"purpose": "setup", "profile": {"consent_send_images": True}})
    assert setup.status_code == 200


def depth_check(client, sid, known):
    return client.post("/api/setup/depth", data={"session_id": sid, "known_distance_m": known},
                       files={"image": ("f.jpg", jpeg(), "image/jpeg")})


def test_depth_check_passes_near_the_true_distance_and_reports_the_scale(clock):
    client = TestClient(create_app(fake_models(depth=FakeDepth(1.6, fov_deg=68.0)), clock=clock))
    sid = client.post("/api/session", json={"purpose": "setup",
                                            "profile": {"consent_send_images": True}}).json()["session_id"]
    body = depth_check(client, sid, 1.5).json()
    assert body == {"measured_m": 1.6, "depth_scale": 0.937, "error_frac": 0.067, "passed": True, "fov_deg": 68.0}
    assert depth_check(client, sid, 3.0).json()["passed"] is False


def test_depth_check_ignores_an_implausible_field_of_view(clock):
    client = TestClient(create_app(fake_models(depth=FakeDepth(1.5, fov_deg=150.0)), clock=clock))
    sid = client.post("/api/session", json={"purpose": "setup",
                                            "profile": {"consent_send_images": True}}).json()["session_id"]
    assert depth_check(client, sid, 1.5).json()["fov_deg"] is None


def test_depth_check_only_in_a_setup_session(client):
    assert depth_check(client, start(client), 1.5).status_code == 409
