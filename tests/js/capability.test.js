import assert from "node:assert/strict";
import { test } from "node:test";

import { Api, uploadLoop } from "../../walksafe/web/js/api.js";
import { Capability, message } from "../../walksafe/web/js/capability.js";
import { Guidance } from "../../walksafe/web/js/guidance.js";

const CFG = {
  server_silent_ms: 2000, announce_repeat_ms: 60000, fault_onset_ms: 1000, fault_clear_ms: 3000,
  check_dead_ms: 1000, battery_warn_levels: [0.2, 0.1], battery_end_level: 0.05,
};

function setup() {
  const clock = { t: 0 };
  const said = [], events = [];
  const cap = new Capability({
    announce: (text, opts) => said.push({ text, urgent: opts.urgent, at: clock.t }),
    now: () => clock.t, cfg: CFG, onEvent: (e) => events.push(e),
  });
  const ok = { available: true };
  // Runs for `ms`, with the phone check reporting `check` and the server
  // answering every 500 ms unless `serverDown`.
  const run = (ms, { check = ok, serverDown = false, serverLevel = "L0", visibility = true } = {}) => {
    for (let t = 0; t < ms; t += 250) {
      clock.t += 250;
      cap.checkRan(check);
      cap.report("visibility", !visibility, "L1", "poor visibility, dark");
      if (clock.t % 500 === 0) {
        cap.requestSent();
        if (!serverDown) cap.serverAnswered(serverLevel);
      }
      cap.tick();
    }
  };
  return { cap, said, events, run, clock };
}

test("full guidance is announced once the server answers", () => {
  const { said, run, cap } = setup();
  cap.requestSent();
  run(1000);
  assert.equal(cap.level, "L0");
  assert.deepEqual(said.map((s) => s.text), ["Full guidance."]);
});

test("T10 poor visibility drops to L1 with its cause, then recovers", () => {
  const { cap, said, events, run } = setup();
  run(1000);
  run(2000, { visibility: false });
  assert.equal(cap.level, "L1");
  assert.match(said.at(-1).text, /Reduced confidence: poor visibility, dark/);
  run(4000);
  assert.equal(cap.level, "L0");
  assert.equal(said.at(-1).text, "Full guidance restored.");
  assert.deepEqual(events.map((e) => e.to_level), ["L0", "L1", "L0"]);
});

test("T10 a brief glitch does not change the level", () => {
  const { cap, said, run } = setup();
  run(1000);
  run(500, { visibility: false });
  run(1000);
  assert.equal(cap.level, "L0");
  assert.equal(said.length, 1);
});

test("T10 server silence drops to L2 after 2 s and is announced urgently", () => {
  const { cap, said, run } = setup();
  run(1000);
  run(3000, { serverDown: true });
  assert.equal(cap.level, "L2");
  assert.equal(said.at(-1).text, "Route guidance lost: server not responding. Obstacle warnings only.");
  assert.equal(said.at(-1).urgent, true);
});

test("T10 the server's own low confidence is L1", () => {
  const { cap, run } = setup();
  run(1000);
  run(2000, { serverLevel: "L1" });
  assert.equal(cap.level, "L1");
});

test("T10 a blocked camera stops guidance (L3)", () => {
  const { cap, said, run } = setup();
  run(1000);
  run(2000, { check: { available: false } });
  assert.equal(cap.level, "L3");
  assert.match(said.at(-1).text, /^Guidance stopped: the camera view is blocked/);
});

test("T10 an on-phone check that stops running is L3 even if nothing else is wrong", () => {
  const { cap, clock, said } = setup();
  cap.tick();
  clock.t += 1500;
  cap.tick();
  assert.equal(cap.level, "L3");
  assert.match(said.at(-1).text, /the obstacle check stopped/);
});

test("T10 the most severe fault wins and its cause is the one announced", () => {
  const { cap, run } = setup();
  run(1000);
  run(3000, { serverDown: true, visibility: false });
  assert.equal(cap.level, "L2");
  assert.equal(cap.cause, "server not responding");
});

test("T10 a reduced level is repeated every minute, never left silent", () => {
  const { said, run } = setup();
  run(1000);
  run(130_000, { serverDown: true });
  const l2 = said.filter((s) => s.text.startsWith("Route guidance lost"));
  assert.equal(l2.length, 3);                       // the drop, then at 60 s and 120 s
  assert.ok(l2[1].at - l2[0].at >= 60_000);
});

test("T10 battery warnings at 20 and 10 percent, shutdown at 5", () => {
  const { cap, said, events } = setup();
  cap.battery(0.19, false);
  cap.battery(0.18, false);
  cap.battery(0.09, false);
  cap.battery(0.04, false);
  assert.deepEqual(said.map((s) => s.text), [
    "Battery at 19 percent.", "Battery at 9 percent.", "WalkSafe is shutting down: battery nearly empty.",
  ]);
  assert.equal(cap.level, "L4");
  assert.equal(events.filter((e) => e.type === "battery").length, 2);
});

test("ending the session is L4 with the reason", () => {
  const { cap, said, run } = setup();
  run(1000);
  cap.end("guidance ended by you");
  assert.equal(cap.level, "L4");
  assert.equal(said.at(-1).text, "WalkSafe is shutting down: guidance ended by you.");
});

test("guidance at L1 only gives cautious commands, and none at L3", () => {
  const out = [];
  const g = new Guidance({
    output: { earcon: () => 0, speak: (t) => out.push(t), vibrate: () => {} },
    now: () => 10_000, cfg: { stale_after_ms: 2000, max_messages_per_min: 15, step_min_interval_ms: 2000 },
  });
  g.level = "L1";
  g.serverResult({ seq: 1, capture_ts: 9_800, command: "walk_forward", phrase: "Walk forward", detail: "" });
  g.serverResult({ seq: 2, capture_ts: 9_800, command: "turn_left", phrase: "Turn left", detail: "" });
  g.level = "L3";
  assert.equal(g.serverResult({ seq: 3, capture_ts: 9_900, command: "stop", phrase: "Stop", detail: "" }),
               "suppressed");
  assert.deepEqual(out, ["Walk forward slowly", "Slow down"]);
});

test("messages", () => {
  assert.equal(message("L0", "", null), "Full guidance.");
  assert.equal(message("L0", "", "L2"), "Full guidance restored.");
});

// T11: server lost mid-session, then back

test("T11 a server that fails mid-session is announced, and recovery is automatic", async () => {
  const cfg = { ...CFG, server_silent_ms: 60, fault_clear_ms: 0 };
  const said = [];
  const cap = new Capability({ announce: (t) => said.push(t), now: () => performance.now(), cfg });
  let down = false, answered = 0;
  const fetchFn = async () => {
    if (down) throw new TypeError("Failed to fetch");
    answered++;
    return { ok: true, status: 200, json: async () => ({ level: "L0" }) };
  };
  const ticker = setInterval(() => { cap.checkRan({ available: true }); cap.tick(); }, 10);
  setTimeout(() => { down = true; }, 100);
  setTimeout(() => { down = false; }, 300);
  const t0 = performance.now();
  await uploadLoop({
    api: new Api("", { fetchFn }), sessionId: "s", retryMs: 10,
    grab: async () => { await new Promise((r) => setTimeout(r, 10)); return { blob: new Blob(["x"]), ts: 0 }; },
    onSent: () => cap.requestSent(), onResult: (r) => cap.serverAnswered(r.level), onError: () => {},
    running: () => performance.now() - t0 < 500,
  });
  clearInterval(ticker);
  assert.deepEqual(said, [
    "Full guidance.",
    "Route guidance lost: server not responding. Obstacle warnings only.",
    "Full guidance restored.",
  ]);
  assert.ok(answered > 5);
});
