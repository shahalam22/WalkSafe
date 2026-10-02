// Wires the page together: the start/stop control, the camera, the checks on
// the phone, the upload loop, guidance and the capability level.
import { Api, sleep, uploadLoop } from "./api.js";
import { Capability } from "./capability.js";
import { clockMs, closeCamera, FrameGrabber, openCamera } from "./capture.js";
import { CONFIG } from "./config.js";
import { ExpansionCheck } from "./expansion.js";
import { Guidance } from "./guidance.js";
import { checkFrame } from "./quality.js";
import { Speaker } from "./speech.js";

const $ = (id) => document.getElementById(id);
const server = new URLSearchParams(location.search).get("server") ?? "";
const api = new Api(server, { timeoutMs: CONFIG.request_timeout_ms });
const speaker = new Speaker();
const settings = loadSettings();

let running = false;
let stream = null;
let grabber = null;
let wakeLock = null;
let sessionId = null;
let quality = { ok: true };
let guidance = null;
let capability = null;
let expansion = null;
let events = [];
let timers = [];

function loadSettings() {
  const defaults = { consent: null, muted: false, verbosity: "normal", rate: 1 };
  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem("walksafe.settings") ?? "{}") };
  } catch {
    return defaults;
  }
}

function saveSettings() {
  try {
    localStorage.setItem("walksafe.settings", JSON.stringify(settings));
  } catch {
    // Private browsing: settings last for this visit only.
  }
}

function applySettings() {
  if (guidance) {
    guidance.muted = settings.muted;
    guidance.verbosity = settings.verbosity;
  }
  speaker.rate = settings.rate;
  $("mute").setAttribute("aria-pressed", String(settings.muted));
  $("mute").textContent = settings.muted ? "Unmute guidance" : "Mute guidance";
  $("verbosity").value = settings.verbosity;
  $("rate").value = String(settings.rate);
}

// Announcements are never muted: silence must not be the only sign of a fault (NFR-7).
function announce(text, { urgent = false } = {}) {
  $("status").textContent = text;
  const after = speaker.earcon("announce");
  speaker.speak(text, { interrupt: urgent, after });
  if (urgent) speaker.vibrate([400, 200, 400]);
}

function queueEvent(e) {
  events.push(e);
  if (events.length > CONFIG.max_queued_events) events.shift();
}

async function flushEvents() {
  if (!sessionId || events.length === 0) return;
  const batch = events;
  events = [];
  try {
    await api.postEvents(sessionId, batch);
  } catch {
    events = batch.concat(events).slice(-CONFIG.max_queued_events);   // try again later
  }
}

async function start() {
  speaker.unlock();
  if (settings.consent === null) {
    $("consent").hidden = false;
    $("consent-allow").focus();
    return;
  }
  running = true;
  $("toggle").textContent = "Stop guidance";
  try {
    stream = await openCamera($("camera"));
  } catch {
    running = false;
    $("toggle").textContent = "Start guidance";
    announce("Camera not available. Guidance has not started.", { urgent: true });
    return;
  }
  grabber = new FrameGrabber($("camera"), CONFIG);
  expansion = new ExpansionCheck(CONFIG);
  guidance = new Guidance({
    output: speaker, now: clockMs, cfg: CONFIG,
    onDelivery: (d) => { if (d.outcome !== "phone_stop") queueEvent({ type: "delivery", ...d }); },
  });
  capability = new Capability({
    announce, now: clockMs, cfg: CONFIG,
    onEvent: (e) => { queueEvent(e); guidance.level = capability.level; },
  });
  applySettings();
  await keepScreenOn();
  announce("Guidance starting.");

  if (settings.consent) {
    capability.requestSent();          // waiting for the server from now on
    connect();
  } else {
    capability.report("phone_only", true, "L2", "camera images are not being sent", 0);
  }
  watchBattery();
  checkLoop();
  timers = [
    setInterval(() => capability.tick(), 250),
    setInterval(flushEvents, CONFIG.event_flush_ms),
  ];
}

async function stop(reason = "user") {
  if (!running) return;
  running = false;
  capability.end(reason === "user" ? "guidance ended by you" : reason);
  timers.forEach(clearInterval);
  $("toggle").textContent = "Start guidance";
  await flushEvents();
  if (sessionId) api.endSession(sessionId, reason).catch(() => {});
  sessionId = null;
  closeCamera(stream);
  wakeLock?.release();
  wakeLock = null;
}

// The checks that run on every frame on the phone. A stop from the expansion
// check goes straight to guidance, without waiting for the server (FR-16).
function checkLoop() {
  if (!running) return;
  try {
    if (grabber.ready()) {
      const g = grabber.gray();
      quality = checkFrame(g.data, g.width, g.height, CONFIG);
      capability.report("visibility", !quality.ok, "L1", `poor visibility, ${quality.cause}`);
      const closing = expansion.update(g.data, g.width, g.height, g.ts);
      capability.checkRan(closing);
      if (closing.stop && !guidance.phoneStopActive) {
        queueEvent({ type: "phone_stop", occurred_at: clockMs(), ttc_s: closing.ttc });
      }
      if (closing.stop) guidance.phoneStop();
      else guidance.phoneClear();
    }
  } catch (e) {
    console.error(e);
    capability.report("check_error", true, "L3", "the obstacle check failed", 0);
  }
  setTimeout(checkLoop, 1000 / CONFIG.capture_fps);
}

async function connect() {
  while (running) {
    try {
      sessionId = await api.startSession({ consent_send_images: true });
    } catch {
      await sleep(2000);               // capability reports the silence
      continue;
    }
    await uploadLoop({
      api, sessionId, running: () => running,
      // Frames the phone already judged unusable are not sent (FR-1).
      grab: async () => (grabber.ready() && quality.ok ? grabber.jpeg() : null),
      onSent: () => capability.requestSent(),
      onResult: (r) => {
        capability.serverAnswered(r.level);
        guidance.serverResult(r);
      },
      onError: () => {},
    });
  }
}

async function watchBattery() {
  const battery = await navigator.getBattery?.().catch(() => null);
  if (!battery) return;                // not on iOS or Firefox
  const check = () => running && capability.battery(battery.level, battery.charging);
  battery.addEventListener("levelchange", check);
  battery.addEventListener("chargingchange", check);
  check();
  const poll = setInterval(() => {
    if (!running) { clearInterval(poll); return; }
    if (capability.level === "L4") stop("battery");
  }, 1000);
}

$("toggle").addEventListener("click", () => (running ? stop() : start()));

$("consent-allow").addEventListener("click", () => {
  settings.consent = true;
  saveSettings();
  $("consent").hidden = true;
  start();
});

$("consent-deny").addEventListener("click", () => {
  settings.consent = false;
  saveSettings();
  $("consent").hidden = true;
  start();                             // phone-only: obstacle warnings, nothing sent
});

$("mute").addEventListener("click", () => {
  settings.muted = !settings.muted;
  saveSettings();
  applySettings();
  speaker.speak(settings.muted ? "Guidance muted" : "Guidance on", { interrupt: true });
});

$("verbosity").addEventListener("change", (e) => {
  settings.verbosity = e.target.value;
  saveSettings();
  applySettings();
});

$("rate").addEventListener("change", (e) => {
  settings.rate = Number(e.target.value);
  saveSettings();
  applySettings();
  speaker.speak("Speech rate changed");
});

// Browsers stop the camera and timers when the screen turns off, so it is kept
// on; the browser drops the lock whenever the page is hidden.
async function keepScreenOn() {
  wakeLock = await navigator.wakeLock?.request("screen").catch(() => null);
  wakeLock?.addEventListener("release", () => { wakeLock = null; });
}

document.addEventListener("visibilitychange", () => {
  if (running && document.visibilityState === "visible" && !wakeLock) keepScreenOn();
});

applySettings();
