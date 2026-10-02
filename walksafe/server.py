"""HTTP API for the phone page, and the page itself."""
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from walksafe import pages, pipeline
from walksafe.config import CFG, Config, Profile, SetupConfig, phone_js
from walksafe.perception import Models
from walksafe.session import Session, SessionStore
from walksafe.storage import LogWriter
from walksafe.ui import diagnostic

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"


class ProfileIn(BaseModel):
    user_id:               str   = Field("anonymous", max_length=64)
    phone_model:           str   = Field("", max_length=128)
    verbosity:             Literal["brief", "normal", "detailed"] = "normal"
    speech_rate:           float = Field(1.0, ge=0.5, le=2.0)
    consent_send_images:   bool  = False
    camera_fov_deg:        float = Field(CFG.profile.camera_fov_deg, ge=30, le=120)
    mount_height_m:        float = Field(1.3, ge=0.5, le=2.0)
    mount_pitch_deg:       float = Field(0.0, ge=-90, le=90)
    shoulder_width_m:      float = Field(CFG.profile.shoulder_width_m, ge=0.25, le=0.8)
    clearance_margin_m:    float = Field(CFG.profile.clearance_margin_m, ge=0.0, le=0.6)
    depth_scale:           float = Field(CFG.profile.depth_scale, ge=0.5, le=2.0)
    depth_check_passed:    bool  = False
    direction_test_passed: bool  = False


class SessionStart(BaseModel):
    purpose: Literal["walk", "setup"] = "walk"
    profile: ProfileIn


class SessionEnd(BaseModel):
    session_id: str
    reason:     str = Field("user", max_length=32)


class EventIn(BaseModel):
    type:        Literal["level_change", "phone_stop", "delivery", "battery"]
    occurred_at: float | None = None          # phone clock, ms
    seq:         int | None   = None
    cause:       str          = Field("", max_length=64)
    from_level:  str | None   = Field(None, max_length=4)
    to_level:    str | None   = Field(None, max_length=4)
    outcome:     str | None   = Field(None, max_length=16)
    spoken_at:   float | None = None
    ttc_s:       float | None = None


class EventBatch(BaseModel):
    session_id: str
    events:     list[EventIn] = Field(max_length=CFG.phone.max_queued_events)


def create_app(models: Models, writer: LogWriter | None = None, cfg: Config = CFG, clock=time.time) -> FastAPI:
    """writer is None only in tests that do not look at the log."""
    app      = FastAPI(title="WalkSafe", docs_url=None, redoc_url=None, openapi_url=None)
    sessions = SessionStore(cfg.server.session_idle_s)
    gpu      = threading.Lock()          # the models are shared, so one frame at a time
    app.state.sessions = sessions
    app.state.writer   = writer
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.server.allowed_origins),
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "sessions": len(sessions), "log_dropped": writer.dropped if writer else 0}

    @app.post("/api/session")
    def start_session(req: SessionStart):
        p = req.profile
        if not p.consent_send_images:
            raise HTTPException(403, "consent_required")
        # Walking needs a passed depth check and direction test (FR-23, NFR-6).
        if req.purpose == "walk" and not (p.depth_check_passed and p.direction_test_passed):
            raise HTTPException(403, "setup_incomplete")
        profile = Profile(p.camera_fov_deg, p.shoulder_width_m, p.clearance_margin_m, p.depth_scale)
        s = sessions.add(Session(models.detector.new_tracker(), profile,
                                 purpose=req.purpose, last_seen=clock()))
        if writer and req.purpose == "walk":
            writer.start_session(s.session_id, p.model_dump())
        log.info("Session %s started (%s)", s.session_id[:8], req.purpose)
        return {"session_id": s.session_id}

    @app.post("/api/session/end")
    def end_session(req: SessionEnd):
        if sessions.remove(req.session_id) is None:
            raise HTTPException(404, "unknown_session")
        if writer:
            writer.end_session(req.session_id, req.reason)
        log.info("Session %s ended (%s)", req.session_id[:8], req.reason)
        return {"ok": True}

    @app.post("/api/event")
    def events(req: EventBatch):
        if sessions.get(req.session_id) is None:
            raise HTTPException(404, "unknown_session")
        for e in req.events:
            if e.type == "level_change":
                log.info("Session %s: %s -> %s (%s)", req.session_id[:8], e.from_level, e.to_level, e.cause)
        if writer:
            writer.events(req.session_id, req.events)
        return {"ok": True, "accepted": len(req.events)}

    async def read_form(request: Request, **fields):
        # Read the body with a cap before parsing: a larger upload would be spooled
        # to a temporary file. Not every proxy keeps the Content-Length header.
        if int(request.headers.get("content-length") or 0) > cfg.server.max_image_bytes:
            raise HTTPException(413, "image_too_large")
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > cfg.server.max_image_bytes:
                raise HTTPException(413, "image_too_large")
        request._body = body                 # Starlette parses the form from this
        form = await request.form()
        try:
            values = {name: kind(form[name]) for name, kind in fields.items()}
            return values, await form["image"].read()
        except (KeyError, ValueError, AttributeError) as e:
            raise HTTPException(422, "bad_request") from e

    def decode(data: bytes) -> np.ndarray:
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(400, "bad_image")
        return image

    @app.post("/api/setup/depth")
    async def setup_depth(request: Request):
        f, data = await read_form(request, session_id=str, known_distance_m=float)
        return await run_in_threadpool(handle_depth_check, f["session_id"], f["known_distance_m"], data)

    def handle_depth_check(session_id, known_m, data):
        s = sessions.get(session_id)
        if s is None:
            raise HTTPException(404, "unknown_session")
        if s.purpose != "setup":
            raise HTTPException(409, "not_a_setup_session")
        if not 0.5 <= known_m <= 5.0:
            raise HTTPException(422, "distance_out_of_range")
        frame = pipeline.resize(decode(data), cfg.models.resize_width)
        with gpu:
            depth = models.depth.estimate(frame)
            fov   = models.depth.last_fov_deg
        return check_depth(depth, known_m, fov, cfg.setup)

    @app.post("/api/frame")
    async def frame(request: Request):
        started = time.perf_counter()
        f, data = await read_form(request, session_id=str, seq=int, capture_ts=float)
        return await run_in_threadpool(handle_frame, f["session_id"], f["seq"], f["capture_ts"], data, started)

    def handle_frame(session_id, seq, capture_ts, data, started):
        now = clock()
        for old in sessions.expire(now):
            log.info("Session %s expired", old.session_id[:8])
            if writer:
                writer.end_session(old.session_id, "idle")
        s = sessions.get(session_id)
        if s is None:
            raise HTTPException(404, "unknown_session")
        image = decode(data)
        # Newest frame only: the phone keeps one request in flight, and anything
        # that arrives while this session is busy is refused rather than queued.
        if not s.lock.acquire(blocking=False):
            raise HTTPException(429, "busy")
        try:
            if seq <= s.last_seq:
                raise HTTPException(409, "out_of_order")
            s.last_seq, s.last_seen = seq, now
            with gpu:
                r = pipeline.process(models, s, image, capture_ts / 1000.0, cfg)
        except HTTPException:
            raise
        except Exception as e:
            log.exception("Pipeline fault in session %s at seq %d", session_id[:8], seq)
            if writer:
                writer.server_event(session_id, "fault", f"pipeline: {type(e).__name__}"[:64])
            return JSONResponse({"error": "pipeline_fault", "seq": seq}, status_code=500)
        finally:
            s.lock.release()

        if writer and s.purpose == "walk":
            writer.decision(session_id, seq, r)
        if cfg.ui.diagnostic_view:
            s.panel = diagnostic.render_jpeg(r, cfg)
        d = r.decision
        return {
            "seq": seq, "capture_ts": capture_ts,
            "command": d.command, "detail": d.detail, "phrase": r.phrase, "reason": d.reason,
            "confidence": d.confidence, "level": r.level, "ego_action": r.ego.action,
            "server_ms": round((time.perf_counter() - started) * 1000, 1), "timings": r.timings,
        }

    # The page asks where the server is (FR-22); here it is the page's own origin.
    @app.get("/server.json")
    def server_location():
        return {"url": ""}

    @app.get("/js/config.js")
    def phone_config():
        return Response(phone_js(cfg), media_type="text/javascript")

    return app


def add_phone_page(app: FastAPI) -> None:
    """Serve the phone page at /. Call this last: it answers every path not taken yet."""
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


def check_depth(depth: np.ndarray, known_m: float, fov_deg: float | None, cfg: SetupConfig = CFG.setup) -> dict:
    """The setup depth check: the wall straight ahead against the distance the user stands from it."""
    H, W = depth.shape
    h, w = int(H * cfg.depth_check_centre / 2), int(W * cfg.depth_check_centre / 2)
    measured = float(np.median(depth[H // 2 - h:H // 2 + h + 1, W // 2 - w:W // 2 + w + 1]))
    error    = abs(measured - known_m) / known_m
    usable_fov = fov_deg is not None and cfg.fov_min_deg <= fov_deg <= cfg.fov_max_deg
    return {
        "measured_m":  round(measured, 2),
        "depth_scale": round(known_m / measured, 3),
        "error_frac":  round(error, 3),
        "passed":      error <= cfg.depth_check_max_error,
        "fov_deg":     round(fov_deg, 1) if usable_fov else None,
    }


def serve(app: FastAPI, port: int = CFG.server.port) -> None:
    """Run the app and open a public HTTPS tunnel to it, then block."""
    import uvicorn
    from gradio.networking import setup_tunnel

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.1)
    # Gradio's share tunnel; a mounted app gets no share link of its own.
    url = setup_tunnel("127.0.0.1", port, secrets.token_urlsafe(32), None, None)
    log.info("WalkSafe is live at %s", url)

    repo, token = os.environ.get("WALKSAFE_PAGES_REPO"), os.environ.get("WALKSAFE_PAGES_TOKEN")
    if repo and token:
        try:
            pages.publish(url, pages.github_remote(repo, token))
            log.info("Phone page: %s (it now points at this server)", pages.page_url(repo))
        except Exception:
            log.exception("Could not publish to GitHub Pages; use the address above instead")
    else:
        log.info("WALKSAFE_PAGES_REPO/TOKEN not set, so the fixed GitHub Pages address was not updated")
    thread.join()
