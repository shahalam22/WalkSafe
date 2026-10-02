// Wires the page together: the start/stop control, the camera, the checks on
// the phone, the upload loop, guidance and the capability level.
import { Api, findServer, sleep, uploadLoop } from "./api.js";
import { Capability } from "./capability.js";
import { clockMs, closeCamera, FrameGrabber, openCamera } from "./capture.js";
import { CONFIG } from "./config.js";
import { ExpansionCheck } from "./expansion.js";
import { Guidance } from "./guidance.js";
import { checkFrame } from "./quality.js";
import { runSetup, SetupRejected } from "./setup.js";
import { Speaker } from "./speech.js";

const $ = (id) => document.getElementById(id);
const serverOverride = new URLSearchParams(location.search).get("server");
const api = new Api("", { timeoutMs: CONFIG.request_timeout_ms });
const locateServer = async () => { api.base = await findServer({ override: serverOverride }); };
const speaker = new Speaker();
const settings = load("walksafe.settings", { muted: false, verbosity: "normal", rate: 1 });
let profile = load("walksafe.profile", null);

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
let phoneStops = 0;
let timers = [];

function load(key, defaults) {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "null");
    return saved && defaults ? { ...defaults, ...saved } : saved ?? defaults;
  } catch {
    return defaults;
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private browsing: kept for this visit only.
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

// The setup is needed before the first walk, and again until it passes.
const setUp = () => typeof profile?.consent_send_images === "boolean"
  && (!profile.consent_send_images || (profile.depth_check_passed && profile.direction_test_passed));

async function start() {
  speaker.unlock();
  if (!setUp()) return setup();
  running = true;
  $("toggle").textContent = "Stop guidance";
  if (!(await openCameraOrSay())) {
    running = false;
    $("toggle").textContent = "Start guidance";
    return;
  }
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

  if (profile.consent_send_images) {
    capability.requestSent();          // waiting for the server from now on
    await locateServer();
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

async function openCameraOrSay() {
  try {
    stream = await openCamera($("camera"));
    grabber = new FrameGrabber($("camera"), CONFIG);
    return true;
  } catch {
    announce("Camera not available. Guidance has not started.", { urgent: true });
    return false;
  }
}

async function setup() {
  $("toggle").hidden = true;
  await locateServer();
  if (!(await openCameraOrSay())) { $("toggle").hidden = false; return; }
  try {
    profile = await runSetup({
      ask, say: (t) => speaker.speak(t), tone: () => speaker.earcon("announce"),
      api, cfg: CONFIG, pitch: readPitch, now: clockMs, sleep,
      grab: () => (grabber.ready() ? grabber.jpeg() : null),
      base: {
        user_id: profile?.user_id ?? crypto.randomUUID(),
        phone_model: navigator.userAgent.slice(0, 128),
      },
    });
    save("walksafe.profile", profile);
  } catch (e) {
    const why = e instanceof SetupRejected ? e.message : "the server could not be reached";
    announce(`Setup did not finish: ${why}. Press the large button to try again.`, { urgent: true });
  } finally {
    closeCamera(stream);
    $("setup").hidden = true;
    $("toggle").hidden = false;
    $("toggle").focus();
  }
}

// One question, answered with buttons; the first is the large one.
function ask(question, choices) {
  return new Promise((resolve) => {
    $("setup").hidden = false;
    $("setup-question").textContent = question;
    const buttons = choices.map((c, i) => {
      const b = document.createElement("button");
      b.textContent = c.label;
      if (i === 0) b.className = "primary";
      b.setAttribute("aria-describedby", "setup-question");
      b.addEventListener("click", () => resolve(c.key), { once: true });
      return b;
    });
    $("setup-choices").replaceChildren(...buttons);
    speaker.speak(question, { interrupt: true });
    buttons[0].focus();
  });
}

// How far the camera points up (+) or down (-) from level, or null if unknown.
async function readPitch() {
  if (typeof DeviceOrientationEvent === "undefined") return null;
  if (DeviceOrientationEvent.requestPermission) {          // iOS asks first
    const answer = await DeviceOrientationEvent.requestPermission().catch(() => "denied");
    if (answer !== "granted") return null;
  }
  return new Promise((resolve) => {
    const done = (value) => { removeEventListener("deviceorientation", on); resolve(value); };
    const on = (e) => done(e.beta === null ? null : e.beta - 90);
    addEventListener("deviceorientation", on);
    setTimeout(() => done(null), 1000);
  });
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
        queueEvent({ type: "phone_stop", seq: ++phoneStops, occurred_at: clockMs(), ttc_s: closing.ttc });
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
      sessionId = await api.startSession({ ...profile, verbosity: settings.verbosity, speech_rate: settings.rate });
    } catch {
      await sleep(2000);               // capability reports the silence
      await locateServer();            // a restarted server has a new address
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

$("redo-setup").addEventListener("click", () => {
  if (running) stop();
  profile = { user_id: profile?.user_id ?? crypto.randomUUID() };
  save("walksafe.profile", profile);     // until the new setup passes, guidance stays blocked
  setup();
});

$("mute").addEventListener("click", () => {
  settings.muted = !settings.muted;
  save("walksafe.settings", settings);
  applySettings();
  speaker.speak(settings.muted ? "Guidance muted" : "Guidance on", { interrupt: true });
});

$("verbosity").addEventListener("change", (e) => {
  settings.verbosity = e.target.value;
  save("walksafe.settings", settings);
  applySettings();
});

$("rate").addEventListener("change", (e) => {
  settings.rate = Number(e.target.value);
  save("walksafe.settings", settings);
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
