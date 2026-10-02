import time
import uuid

import cv2
import jwt
import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from server.api import create_app
from server.auth import AuthError, Verifier
from server.supa import SupabaseError

URL = "https://example.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


def token(role="blind", sub=None, **over):
    claims = {"sub": sub or str(uuid.uuid4()), "email": f"{role}@x.org", "aud": "authenticated",
              "iss": f"{URL}/auth/v1", "exp": int(time.time()) + 600, "app_metadata": {"role": role}}
    claims.update(over)
    return jwt.encode(claims, KEY, algorithm="ES256")


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


class FakeDb:
    def __init__(self):
        self.profiles = {}
        self.calls = []
        self.down = False

    def select(self, table, match, columns="*"):
        if self.down:
            raise SupabaseError(503, "down")
        p = self.profiles.get(match["id"])
        return [p] if p else []

    def update(self, table, match, values):
        self.calls.append(("update", table, match, values))

    def create_user(self, email, password, role, name):
        if email == "taken@x.org":
            raise SupabaseError(422, "A user with this email address has already been registered")
        self.calls.append(("create", email, role, name))
        return {"id": str(uuid.uuid4()), "email": email}

    def update_user(self, uid, **attrs):
        self.calls.append(("update_user", uid, attrs))
        return {}

    def delete_user(self, uid):
        self.calls.append(("delete", uid))


class FakeWriter:
    dropped = 0

    def __init__(self):
        self.events = []

    def start_session(self, sid, uid, ts):
        self.events.append(("start", sid, uid))

    def frame(self, sid, ts, result):
        self.events.append(("frame", sid, result["frame_idx"]))

    def end_session(self, sid, ts, frames, reason):
        self.events.append(("end", sid, frames, reason))


def fake_process(frame, view):
    fake_process.n += 1
    return {"frame_idx": fake_process.n, "command": "step_left", "phrase": "Step left", "detail": "gap left",
            "reasoning": "gap_left", "ego": {}, "gaps": [],
            "agents": [{"risk_level": "critical"}, {"risk_level": "low"}],
            "view": b"\xff\xd8jpeg" if view else None}


fake_process.n = 0


@pytest.fixture
def env():
    db, writer, resets = FakeDb(), FakeWriter(), []
    app = create_app(verifier=Verifier(URL, FakeJwks()), db=db, writer=writer,
                     process=fake_process, reset=lambda: resets.append(1))
    with TestClient(app) as client:
        yield client, db, writer, resets


def jpeg():
    ok, buf = cv2.imencode(".jpg", np.zeros((64, 48, 3), np.uint8))
    return buf.tobytes()


def test_health_needs_no_login(env):
    client, *_ = env
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["app"] == "walksafe"


def test_bad_or_missing_token(env):
    client, *_ = env
    assert client.post("/api/session/start").status_code == 401
    assert client.post("/api/session/start", headers=auth("nonsense")).status_code == 401
    expired = token(exp=int(time.time()) - 10)
    assert client.post("/api/session/start", headers=auth(expired)).json()["detail"] == "login_expired"
    other_key = jwt.encode({"sub": "x", "aud": "authenticated", "iss": f"{URL}/auth/v1",
                            "exp": int(time.time()) + 60}, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")
    assert client.post("/api/session/start", headers=auth(other_key)).status_code == 401


def test_guidance_session_flow(env):
    client, db, writer, resets = env
    uid = str(uuid.uuid4())
    h = auth(token("blind", sub=uid))
    sid = client.post("/api/session/start", headers=h).json()["session_id"]
    assert resets == [1]

    r = client.post(f"/api/frame?session_id={sid}", content=jpeg(), headers={**h, "Content-Type": "image/jpeg"})
    body = r.json()
    assert r.status_code == 200
    assert body["phrase"] == "Step left" and body["critical"] == 1 and body["view"] is None

    r = client.post(f"/api/frame?session_id={sid}&view=1", content=jpeg(), headers=h)
    assert r.json()["view"]                                 # base64 JPEG for the demo view

    assert client.post("/api/session/stop", json={"session_id": sid}, headers=h).json() == {"stopped": True}
    kinds = [e[0] for e in writer.events]
    assert kinds == ["start", "frame", "frame", "end"]
    assert writer.events[0][2] == uid and writer.events[-1][2:] == (2, "user")


def test_new_session_replaces_old(env):
    client, db, writer, _ = env
    h = auth(token())
    old = client.post("/api/session/start", headers=h).json()["session_id"]
    new = client.post("/api/session/start", headers=h).json()["session_id"]
    assert old != new
    assert ("end", old, 0, "replaced") in writer.events
    assert client.post(f"/api/frame?session_id={old}", content=jpeg(), headers=h).status_code == 409


def test_frame_checks(env):
    client, *_ = env
    h = auth(token())
    sid = client.post("/api/session/start", headers=h).json()["session_id"]
    assert client.post(f"/api/frame?session_id={sid}", content=b"not a jpeg", headers=h).status_code == 422
    big = b"\0" * 2_000_001
    assert client.post(f"/api/frame?session_id={sid}", content=big, headers=h).status_code == 413


def test_disabled_account_cannot_start(env):
    client, db, *_ = env
    uid = str(uuid.uuid4())
    db.profiles[uid] = {"is_active": False}
    r = client.post("/api/session/start", headers=auth(token(sub=uid)))
    assert r.status_code == 403 and r.json()["detail"] == "account_disabled"
    db.down = True                     # database down: guidance still starts
    assert client.post("/api/session/start", headers=auth(token(sub=uid))).status_code == 200


def test_idle_session_expires():
    from server.api import Sessions
    now = [0.0]
    w = FakeWriter()
    s = Sessions(w, reset=lambda: None, clock=lambda: now[0], idle_s=60)
    sid = s.start("u1")
    now[0] = 30
    s.expire_idle()
    assert s.touch(sid)
    now[0] = 100
    s.expire_idle()
    assert s.active is None and w.events[-1] == ("end", sid, 1, "idle")


def test_admin_endpoints_need_admin(env):
    client, *_ = env
    r = client.post("/api/admin/users", json={"email": "a@b.co", "password": "secret1"}, headers=auth(token("blind")))
    assert r.status_code == 403


def test_admin_creates_and_manages_blind_user(env):
    client, db, *_ = env
    h = auth(token("admin"))
    r = client.post("/api/admin/users", json={"email": " Rahim@X.org ", "password": "secret1",
                                              "display_name": "Rahim"}, headers=h)
    assert r.status_code == 201
    assert db.calls[-1] == ("create", "rahim@x.org", "blind", "Rahim")

    r = client.post("/api/admin/users", json={"email": "taken@x.org", "password": "secret1"}, headers=h)
    assert r.status_code == 400 and "already" in r.json()["detail"]
    assert client.post("/api/admin/users", json={"email": "bad", "password": "secret1"}, headers=h).status_code == 422
    assert client.post("/api/admin/users", json={"email": "a@b.co", "password": "123"}, headers=h).status_code == 422

    uid = str(uuid.uuid4())
    db.profiles[uid] = {"id": uid, "role": "blind"}
    assert client.patch(f"/api/admin/users/{uid}", json={"active": False}, headers=h).status_code == 200
    assert ("update_user", uid, {"ban_duration": "876000h"}) in db.calls
    assert ("update", "profiles", {"id": uid}, {"is_active": False}) in db.calls
    assert client.delete(f"/api/admin/users/{uid}", headers=h).status_code == 200

    admin_id = str(uuid.uuid4())
    db.profiles[admin_id] = {"id": admin_id, "role": "admin"}
    assert client.delete(f"/api/admin/users/{admin_id}", headers=h).status_code == 403
    assert client.delete(f"/api/admin/users/{uuid.uuid4()}", headers=h).status_code == 404


def test_cors_preflight_from_app_page(env):
    client, *_ = env
    r = client.options("/api/frame", headers={
        "Origin": "https://shahalam22.github.io", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] in ("*", "https://shahalam22.github.io")
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


def test_verifier_rejects_wrong_audience():
    v = Verifier(URL, FakeJwks())
    with pytest.raises(AuthError):
        v.verify(token(aud="anon"))
    assert v.verify(token("admin")).is_admin
    assert v.verify(token("superuser")).role == "blind"
