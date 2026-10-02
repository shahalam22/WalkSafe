"""HTTP API for the WalkSafe app (phone and admin pages).

Every call except /api/health needs a Supabase login token. The models and
their tracking state are shared, so one guidance session runs at a time: a new
session ends the one before it.
"""
import asyncio
import base64
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import cv2
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import SERVER
from server.auth import AuthError, User
from server.supa import SupabaseError

VERSION = "1.0.0"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BANNED_FOREVER = "876000h"     # 100 years: how the Auth API disables an account


@dataclass
class _Active:
    session_id: str
    user_id:    str
    started_at: float
    last_seen:  float
    frames:     int = 0


class Sessions:
    """The one guidance session running now."""

    def __init__(self, writer, reset, clock=time.time, idle_s=SERVER["session_idle_s"]):
        self.writer = writer
        self.reset  = reset
        self.clock  = clock
        self.idle_s = idle_s
        self.active = None
        self._lock  = threading.Lock()

    def start(self, user_id):
        with self._lock:
            if self.active:
                self._end("replaced")
            now = self.clock()
            self.reset()
            self.active = _Active(str(uuid.uuid4()), user_id, now, now)
            self.writer.start_session(self.active.session_id, user_id, now)
            return self.active.session_id

    def stop(self, session_id, reason="user"):
        with self._lock:
            if not self.active or self.active.session_id != session_id:
                return False
            self._end(reason)
            return True

    def touch(self, session_id):
        """A frame arrived for session_id. False if that session is not the running one."""
        with self._lock:
            if not self.active or self.active.session_id != session_id:
                return False
            self.active.frames   += 1
            self.active.last_seen = self.clock()
            return True

    def expire_idle(self):
        with self._lock:
            if self.active and self.clock() - self.active.last_seen > self.idle_s:
                self._end("idle")

    def _end(self, reason):
        a = self.active
        self.writer.end_session(a.session_id, self.clock(), a.frames, reason)
        self.active = None


class FrameAck(BaseModel):
    session_id: str


class NewUser(BaseModel):
    email:        str = Field(max_length=254)
    password:     str = Field(min_length=6, max_length=72)
    display_name: str = Field("", max_length=80)


class UserChange(BaseModel):
    display_name: str | None = Field(None, max_length=80)
    password:     str | None = Field(None, min_length=6, max_length=72)
    active:       bool | None = None


def create_app(*, verifier, db, writer, process, reset, is_ready=lambda: True,
               clock=time.time, web_dir=None):
    """process(frame_bgr, want_view) -> result dict; reset() clears the pipeline.
    db is a server.supa.Supabase (secret key); writer a storage.LogWriter."""
    sessions = Sessions(writer, reset, clock)

    @asynccontextmanager
    async def lifespan(app):
        async def reaper():
            while True:
                await asyncio.sleep(10)
                sessions.expire_idle()
        task = asyncio.create_task(reaper())
        yield
        task.cancel()

    app = FastAPI(title="WalkSafe", version=VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions = sessions
    # The app page lives on another address (GitHub Pages), so allow cross-origin
    # calls. Logins travel in the Authorization header, never in cookies.
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"], max_age=600)

    def current_user(request: Request) -> User:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise HTTPException(401, "login_required")
        try:
            return verifier.verify(header[7:].strip())
        except AuthError as e:
            raise HTTPException(401, "login_expired") from e

    def admin_user(user: User = Depends(current_user)) -> User:
        if not user.is_admin:
            raise HTTPException(403, "admin_only")
        return user

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/api/health")
    def health():
        return {"ok": True, "app": "walksafe", "version": VERSION,
                "ready": bool(is_ready()), "busy": sessions.active is not None,
                "log_dropped": writer.dropped}

    # ── Guidance ──────────────────────────────────────────────────────────────

    @app.post("/api/session/start")
    async def start_session(user: User = Depends(current_user)):
        if not is_ready():
            raise HTTPException(503, "models_loading")
        try:
            rows = await run_in_threadpool(db.select, "profiles", {"id": user.id}, "is_active")
            if rows and not rows[0]["is_active"]:
                raise HTTPException(403, "account_disabled")
        except SupabaseError as e:              # the database is down: guide anyway
            print(f"⚠️  Could not check the account: {e}")
        sid = await run_in_threadpool(sessions.start, user.id)
        return {"session_id": sid}

    @app.post("/api/session/stop")
    def stop_session(req: FrameAck, user: User = Depends(current_user)):
        return {"stopped": sessions.stop(req.session_id)}

    @app.post("/api/frame")
    async def frame(request: Request, session_id: str, view: bool = False,
                    user: User = Depends(current_user)):
        body = await request.body()
        if len(body) > SERVER["max_image_bytes"]:
            raise HTTPException(413, "image_too_large")
        if not sessions.touch(session_id):
            raise HTTPException(409, "session_ended")
        img = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(422, "bad_image")

        t0     = time.perf_counter()
        result = await run_in_threadpool(process, img, view)
        ms     = round((time.perf_counter() - t0) * 1000)
        writer.frame(session_id, clock(), result)

        return {
            "frame_idx": result["frame_idx"],
            "command":   result["command"],
            "phrase":    result["phrase"],
            "detail":    result["detail"],
            "agents":    len(result["agents"]),
            "critical":  sum(1 for a in result["agents"] if a.get("risk_level") == "critical"),
            "server_ms": ms,
            "view":      base64.b64encode(result["view"]).decode() if result.get("view") else None,
        }

    # ── Admin: blind-user accounts ────────────────────────────────────────────

    def supabase_call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SupabaseError as e:
            raise HTTPException(400 if 400 <= e.status < 500 else 502, e.message) from e

    def target_profile(user_id):
        rows = supabase_call(db.select, "profiles", {"id": user_id}, "id,role")
        if not rows:
            raise HTTPException(404, "no_such_user")
        if rows[0]["role"] == "admin":
            raise HTTPException(403, "cannot_change_admin")
        return rows[0]

    @app.post("/api/admin/users", status_code=201)
    def create_user(req: NewUser, admin: User = Depends(admin_user)):
        email = req.email.strip().lower()
        if not _EMAIL.match(email):
            raise HTTPException(422, "bad_email")
        u = supabase_call(db.create_user, email, req.password, "blind",
                          req.display_name.strip() or email)
        return {"id": u["id"], "email": u.get("email", email)}

    @app.patch("/api/admin/users/{user_id}")
    def change_user(user_id: UUID, req: UserChange, admin: User = Depends(admin_user)):
        uid = str(user_id)
        target_profile(uid)
        attrs, profile = {}, {}
        if req.password is not None:
            attrs["password"] = req.password
        if req.active is not None:
            attrs["ban_duration"] = "none" if req.active else _BANNED_FOREVER
            profile["is_active"]  = req.active
        if req.display_name is not None:
            name = req.display_name.strip()
            attrs["user_metadata"]  = {"display_name": name}
            profile["display_name"] = name
        if attrs:
            supabase_call(db.update_user, uid, **attrs)
        if profile:
            supabase_call(db.update, "profiles", {"id": uid}, profile)
        return {"ok": True}

    @app.delete("/api/admin/users/{user_id}")
    def delete_user(user_id: UUID, admin: User = Depends(admin_user)):
        uid = str(user_id)
        target_profile(uid)
        supabase_call(db.delete_user, uid)
        return {"ok": True}

    # The same app page, also served here so the server works on its own.
    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
