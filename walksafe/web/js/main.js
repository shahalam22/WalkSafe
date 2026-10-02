// Wires the page together: the start/stop control, the camera, the checks on
// the phone, the upload loop and guidance.
import { Api, sleep, uploadLoop } from "./api.js";
import { clockMs, closeCamera, FrameGrabber, openCamera } from "./capture.js";
import { CONFIG } from "./config.js";
import { Guidance } from "./guidance.js";
import { checkFrame } from "./quality.js";
import { Speaker } from "./speech.js";

const $ = (id) => document.getElementById(id);
const server = new URLSearchParams(location.search).get("server") ?? "";
const api = new Api(server, { timeoutMs: CONFIG.request_timeout_ms });
const speaker = new Speaker();
const guidance = new Guidance({ output: speaker, now: clockMs, cfg: CONFIG });
const settings = loadSettings();

let running = false;
let stream = null;
let grabber = null;
let wakeLock = null;
let sessionId = null;
let quality = { ok: true };

function loadSettings() {
  const defaults = { consent: false, muted: false, verbosity: "normal", rate: 1 };
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
  guidance.muted = settings.muted;
  guidance.verbosity = settings.verbosity;
  speaker.rate = settings.rate;
  $("mute").setAttribute("aria-pressed", String(settings.muted));
  $("mute").textContent = settings.muted ? "Unmute guidance" : "Mute guidance";
  $("verbosity").value = settings.verbosity;
  $("rate").value = String(settings.rate);
}

function say(text) {
  $("status").textContent = text;
  speaker.speak(text);
}

async function start() {
  speaker.unlock();
  if (!settings.consent) {
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
    say("Camera not available. Guidance has not started.");
    return;
  }
  grabber = new FrameGrabber($("camera"), CONFIG);
  wakeLock = await navigator.wakeLock?.request("screen").catch(() => null);
  say("Guidance started.");
  checkLoop();
  connect();
}

async function stop(reason = "user") {
  running = false;
  $("toggle").textContent = "Start guidance";
  if (sessionId) api.endSession(sessionId, reason).catch(() => {});
  sessionId = null;
  closeCamera(stream);
  wakeLock?.release();
  wakeLock = null;
  speaker.speak("Guidance stopped.", { interrupt: true });
  $("status").textContent = "Guidance stopped.";
}

// The checks that run on every frame on the phone.
function checkLoop() {
  if (!running) return;
  if (grabber.ready()) {
    const g = grabber.gray();
    quality = checkFrame(g.data, g.width, g.height, CONFIG);
  }
  setTimeout(checkLoop, 1000 / CONFIG.capture_fps);
}

async function connect() {
  while (running) {
    try {
      sessionId = await api.startSession({ consent_send_images: settings.consent });
    } catch (e) {
      $("status").textContent = `Server not reachable (${e.detail}). Retrying.`;
      await sleep(2000);
      continue;
    }
    await uploadLoop({
      api, sessionId, running: () => running,
      // Frames the phone already judged unusable are not sent (FR-1).
      grab: async () => (grabber.ready() && quality.ok ? grabber.jpeg() : null),
      onResult: (r) => {
        guidance.serverResult(r);
        $("status").textContent = `${r.phrase} (${r.level})`;
      },
      onError: (e) => { $("status").textContent = `Server error: ${e.detail}`; },
    });
  }
}

$("toggle").addEventListener("click", () => (running ? stop() : start()));

$("consent-allow").addEventListener("click", () => {
  settings.consent = true;
  saveSettings();
  $("consent").hidden = true;
  start();
});

$("consent-deny").addEventListener("click", () => {
  $("consent").hidden = true;
  say("No images will be sent. Guidance needs the server for now.");
  $("toggle").focus();
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

document.addEventListener("visibilitychange", async () => {
  if (running && document.visibilityState === "visible" && !wakeLock) {
    wakeLock = await navigator.wakeLock?.request("screen").catch(() => null);
  }
});

applySettings();
