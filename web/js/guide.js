// The blind user's screen. One full-screen button: tap anywhere to start,
// tap again (or shake the phone) to stop. Everything is spoken.
//
// While guiding, the screen is kept awake (it shows black) because a browser
// cannot use the camera with the screen off. If the screen does go off, the
// session ends, and it starts again by itself when the screen comes back.
import { supabase } from "./supabase.js";
import { api, explain, health, loadServerUrl } from "./server.js";
import { Speaker } from "./speech.js";
import { $, announce, canInstall, install, prefs } from "./ui.js";

const UPLOAD_WIDTH = 518;           // the server works at this width
const JPEG_QUALITY = 0.7;
const FIRST_FRAME_TIMEOUT = 120000; // the first frame waits for a depth map
const FRAME_TIMEOUT = 20000;
const MIN_FRAME_MS = 150;           // at most ~7 frames a second, so the page stays responsive
const MAX_FAILURES = 4;             // in a row, before giving up
const TAP_GUARD_MS = 1500;          // ignore a second tap this soon (double taps)
const SHAKE_MS2 = 25;               // acceleration that counts as a shake
const SHAKE_PEAKS = 3;              // ...this many times within SHAKE_WINDOW_MS
const SHAKE_WINDOW_MS = 1200;

const speaker = new Speaker();

class Guide {
  constructor() {
    this.state = "idle";            // idle | starting | running | stopping
    this.gen = 0;                   // which start() is current
    this.base = "";
    this.sessionId = null;
    this.stream = null;
    this.wakeLock = null;
    this.abort = null;
    this.lastToggle = 0;
    this.lastPhrase = "";
    this.lastSpokenAt = 0;
    this.resumeOnShow = false;
    this.shakes = [];
    this.canvas = document.createElement("canvas");

    this.video = $("#guide-video");
    this.toggle = $("#guide-toggle");
    this.title = $("#guide-title");
    this.command = $("#guide-command");
    this.status = $("#guide-status");
    this.panel = $("#guide-panel");

    this.toggle.addEventListener("click", () => this.onTap());
    document.addEventListener("visibilitychange", () => this.onVisibility());
    addEventListener("devicemotion", (e) => this.onMotion(e));
    this.render();
  }

  // ── Start / stop ───────────────────────────────────────────────────────────

  onTap() {
    const now = Date.now();
    if (now - this.lastToggle < TAP_GUARD_MS) return;
    this.lastToggle = now;
    speaker.unlock();
    if (this.state === "idle") this.start();
    else if (this.state === "running" || this.state === "starting") this.stop("user");
  }

  async start({ resumed = false } = {}) {
    if (this.state !== "idle") return;
    this.state = "starting";
    const gen = ++this.gen;
    const alive = () => this.state === "starting" && this.gen === gen;
    this.lastPhrase = "";
    this.abort = new AbortController();
    this.applyPrefs();
    this.render("Starting…");
    speaker.say(resumed ? "Starting WalkSafe again." : "Starting WalkSafe.", { interrupt: true });
    navigator.vibrate?.(80);

    try {
      const { url } = await loadServerUrl();
      this.base = url;
      const h = await health(url);
      if (!h.ready) throw Object.assign(new Error(), { detail: "models_loading", status: 503 });
      if (!alive()) return;

      const stream = await openCamera(this.video);
      if (!alive()) return stream.getTracks().forEach((t) => t.stop());
      this.stream = stream;

      const { session_id } = await api(this.base, "/api/session/start", { json: {}, signal: this.abort.signal });
      if (!alive()) return;
      this.sessionId = session_id;
      await this.keepAwake();
      if (!alive()) return;

      this.state = "running";
      this.render("Guiding");
      speaker.say("WalkSafe is on. Tap anywhere to stop.");
      this.loop();
    } catch (err) {
      if (!alive()) return;
      const why = err?.name === "NotAllowedError" || err?.name === "NotFoundError"
        ? "The camera is not available. Ask your helper to allow the camera."
        : explain(err);
      this.finish(`${why} WalkSafe is off.`);
    }
  }

  stop(reason, message) {
    if (this.state === "idle" || this.state === "stopping") return;
    this.state = "stopping";
    this.abort?.abort();
    if (this.sessionId) {
      api(this.base, "/api/session/stop", { json: { session_id: this.sessionId }, timeout: 5000 }).catch(() => {});
    }
    this.finish(message ?? (reason === "hidden" ? null : "WalkSafe stopped."));
  }

  finish(message) {
    this.sessionId = null;
    this.closeCamera();
    this.wakeLock?.release().catch(() => {});
    this.wakeLock = null;
    this.state = "idle";
    this.render(message ? message.replace(" WalkSafe is off.", "") : "Stopped");
    if (message) {
      speaker.say(message, { interrupt: true });
      announce(message);
      navigator.vibrate?.([60, 60, 60]);
    }
  }

  closeCamera() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.video.srcObject = null;
  }

  // ── The frame loop: one frame in flight at a time ─────────────────────────

  async loop() {
    let failures = 0;
    let first = true;
    const sid = this.sessionId;
    while (this.state === "running" && this.sessionId === sid) {
      const began = Date.now();
      const jpeg = await this.grab();
      if (!jpeg) { await sleep(100); continue; }
      try {
        const res = await api(this.base, `/api/frame?session_id=${sid}&view=${this.view ? 1 : 0}`, {
          body: jpeg, type: "image/jpeg",
          timeout: first ? FIRST_FRAME_TIMEOUT : FRAME_TIMEOUT,
          signal: this.abort.signal,
        });
        if (this.state !== "running") return;
        if (failures > 0) speaker.say("Connected again.");
        failures = 0;
        first = false;
        this.onResult(res);
        await sleep(MIN_FRAME_MS - (Date.now() - began));
      } catch (err) {
        if (this.state !== "running") return;
        if (err.status === 409) return this.stop("ended", "The session ended on the server. WalkSafe stopped.");
        if (err.status === 401) {
          await supabase.auth.refreshSession().catch(() => {});
          if (++failures < 2) continue;
          return this.stop("auth", "The sign-in has expired. Ask your helper. WalkSafe stopped.");
        }
        failures++;
        if (failures === 1) speaker.say("Connection lost. Trying again.", { interrupt: true });
        if (failures >= MAX_FAILURES) {
          return this.stop("offline", "Cannot reach the WalkSafe server. WalkSafe stopped.");
        }
        await sleep(1000 * failures);
      }
    }
  }

  onResult(res) {
    const phrase = res.phrase || "";
    const repeat = Number(prefs.get("repeat", 0)) * 1000;
    const now = Date.now();
    if (phrase !== this.lastPhrase || (repeat && now - this.lastSpokenAt >= repeat)) {
      const urgent = res.command === "stop";
      if (urgent && phrase !== this.lastPhrase) speaker.alarm();
      speaker.say(phrase, { interrupt: urgent });
      this.lastPhrase = phrase;
      this.lastSpokenAt = now;
    }
    this.command.textContent = phrase;
    this.status.textContent = res.detail || "";
    if (this.view && res.view) this.panel.src = `data:image/jpeg;base64,${res.view}`;
  }

  async grab() {
    const v = this.video;
    if (v.readyState < 2 || !v.videoWidth) return null;
    const w = UPLOAD_WIDTH;
    const h = Math.round((v.videoHeight * w) / v.videoWidth);
    this.canvas.width = w;
    this.canvas.height = h;
    this.canvas.getContext("2d").drawImage(v, 0, 0, w, h);      // never mirrored
    return new Promise((resolve) => this.canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
  }

  // ── Screen, motion ─────────────────────────────────────────────────────────

  async keepAwake() {
    try {
      this.wakeLock = await navigator.wakeLock?.request("screen");
    } catch { /* not allowed now; tried again when visible */ }
  }

  onVisibility() {
    if (document.hidden) {
      if (this.state === "running" || this.state === "starting") {
        this.resumeOnShow = true;
        this.stop("hidden");
      }
    } else if (this.resumeOnShow) {
      this.resumeOnShow = false;
      this.start({ resumed: true });
    }
  }

  onMotion(e) {
    if (this.state !== "running") return;
    const a = e.accelerationIncludingGravity;
    if (!a) return;
    const g = Math.hypot(a.x || 0, a.y || 0, a.z || 0);
    if (g < SHAKE_MS2) return;
    const now = Date.now();
    if (this.shakes.length && now - this.shakes.at(-1) < 150) return;     // same peak
    this.shakes = [...this.shakes.filter((t) => now - t < SHAKE_WINDOW_MS), now];
    if (this.shakes.length >= SHAKE_PEAKS) {
      this.shakes = [];
      this.lastToggle = now;
      this.stop("shake");
    }
  }

  // ── Display (for helpers and demos; the user hears everything) ────────────

  get view() { return prefs.get("view", false); }

  applyPrefs() {
    speaker.rate = Number(prefs.get("rate", 1));
    document.body.classList.toggle("show-view", this.view);
  }

  render(status) {
    const on = this.state === "running" || this.state === "starting";
    document.body.classList.toggle("guiding", on);
    this.title.textContent = on ? "Tap anywhere to stop" : "Tap anywhere to start";
    this.toggle.setAttribute("aria-label", on ? "Stop WalkSafe" : "Start WalkSafe");
    if (!on) {
      this.command.textContent = "";
      this.panel.removeAttribute("src");
    }
    if (status !== undefined) this.status.textContent = status;
  }
}

async function openCamera(video) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
  });
  video.srcObject = stream;
  await video.play();
  return stream;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Helper menu ──────────────────────────────────────────────────────────────

function initHelper(guide, session, onOpenAdmin) {
  const dlg = $("#helper");
  const isAdmin = session.user.app_metadata?.role === "admin";
  $("#helper-who").textContent = `Signed in as ${session.user.email}`;
  $("#helper-admin").hidden = !isAdmin;

  const showInstall = () => {
    $("#helper-install").hidden = !canInstall();
    $("#helper-install-hint").hidden = canInstall();
  };
  document.addEventListener("walksafe-installable", showInstall);

  $("#guide-menu-btn").onclick = () => {
    if (guide.state !== "idle") guide.stop("user");
    $("#pref-view").checked = prefs.get("view", false);
    $("#pref-repeat").value = String(prefs.get("repeat", 0));
    $("#pref-rate").value = prefs.get("rate", 1);
    $("#pref-rate-val").textContent = `${prefs.get("rate", 1)}×`;
    showInstall();
    dlg.showModal();
  };

  $("#pref-view").onchange = (e) => { prefs.set("view", e.target.checked); guide.applyPrefs(); };
  $("#pref-repeat").onchange = (e) => prefs.set("repeat", Number(e.target.value));
  $("#pref-rate").oninput = (e) => {
    prefs.set("rate", Number(e.target.value));
    $("#pref-rate-val").textContent = `${e.target.value}×`;
    guide.applyPrefs();
  };

  $("#helper-check").onclick = async () => {
    const out = $("#helper-server");
    out.textContent = "Checking…";
    const { url, cached } = await loadServerUrl();
    try {
      const h = await health(url);
      out.textContent = `${h.ready ? "Server is running." : "Server is still loading."} ${url}`
        + (cached ? " (saved address; Supabase not reachable)" : "");
    } catch (err) {
      out.textContent = `${explain(err)} ${url || ""}`;
    }
  };

  $("#helper-camera").onclick = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } } });
      s.getTracks().forEach((t) => t.stop());
      speaker.unlock();
      speaker.say("Camera allowed.");
      $("#helper-camera").textContent = "Camera allowed ✓";
    } catch {
      $("#helper-camera").textContent = "Camera blocked: allow it in Chrome's site settings";
    }
  };

  $("#helper-voice").onclick = () => {
    speaker.unlock();
    speaker.rate = Number(prefs.get("rate", 1));
    speaker.alarm();
    speaker.say("This is how WalkSafe sounds. Walk forward. Step left. Stop.", { interrupt: true });
  };

  $("#helper-install").onclick = async () => {
    await install();
    showInstall();
  };

  $("#helper-admin").onclick = () => { dlg.close(); onOpenAdmin(); };
  $("#helper-signout").onclick = async () => {
    dlg.close();
    await supabase.auth.signOut();
  };
}

let guide = null;

export function initGuide(session, { onOpenAdmin }) {
  guide ??= new Guide();
  initHelper(guide, session, onOpenAdmin);
  guide.applyPrefs();
  guide.render("");
  return guide;
}

export function leaveGuide() {
  if (guide && guide.state !== "idle") guide.stop("user");
  document.body.classList.remove("guiding", "show-view");
}
