import assert from "node:assert/strict";
import { test } from "node:test";

import { Guidance } from "../../walksafe/web/js/guidance.js";

const CFG = { stale_after_ms: 2000, max_messages_per_min: 15, step_min_interval_ms: 2000 };

function setup() {
  const clock = { t: 1_759_400_000_000 };
  const said = [], vibrations = [], deliveries = [];
  const output = {
    earcon: () => 0,
    speak: (text, opts) => said.push({ text, interrupt: opts.interrupt }),
    vibrate: (pattern) => vibrations.push(pattern),
  };
  const g = new Guidance({ output, now: () => clock.t, cfg: CFG, onDelivery: (d) => deliveries.push(d) });
  let seq = 0;
  const server = (command, { age = 400, detail = "", seqOverride } = {}) =>
    g.serverResult({ seq: seqOverride ?? ++seq, capture_ts: clock.t - age, command, detail, phrase: command });
  const advance = (ms) => { clock.t += ms; };
  return { g, said, vibrations, deliveries, server, advance };
}

// T7: phone stop wins

test("T7 a phone stop interrupts a server command already spoken", () => {
  const { g, said, server, advance } = setup();
  server("walk_forward");
  advance(300);
  g.phoneStop();
  assert.deepEqual(said.map((s) => s.text), ["walk_forward", "Stop"]);
  assert.equal(said[1].interrupt, true);
});

test("T7 server guidance during a phone stop is never spoken", () => {
  const { g, said, server, deliveries } = setup();
  g.phoneStop();
  assert.equal(server("walk_forward"), "overridden");
  assert.equal(server("step_left"), "overridden");
  assert.deepEqual(said.map((s) => s.text), ["Stop"]);
  assert.ok(deliveries.some((d) => d.outcome === "phone_stop"));
});

test("T7 results captured during the stop are not trusted after it clears", () => {
  const { g, said, server, advance } = setup();
  g.phoneStop();
  advance(1000);
  g.phoneClear();
  advance(200);
  assert.equal(server("walk_forward", { age: 600 }), "overridden");   // captured before the clear
  assert.equal(server("walk_forward", { age: 100 }), "spoken");       // captured after it
  assert.deepEqual(said.map((s) => s.text), ["Stop", "walk_forward"]);
});

test("T7 the phone stop vibrates even when muted", () => {
  const { g, said, vibrations } = setup();
  g.muted = true;
  g.phoneStop();
  assert.equal(said.length, 0);
  assert.equal(vibrations.length, 1);
});

// T8: stale and out-of-order guidance

test("T8 a result older than 2 s is discarded, not spoken late", () => {
  const { server, said } = setup();
  assert.equal(server("step_left", { age: 2100 }), "stale");
  assert.equal(said.length, 0);
});

test("T8 a result older than one already handled is ignored", () => {
  const { server, said } = setup();
  assert.equal(server("walk_forward", { seqOverride: 5 }), "spoken");
  assert.equal(server("stop", { seqOverride: 4 }), "out_of_order");
  assert.equal(server("stop", { seqOverride: 5 }), "out_of_order");
  assert.deepEqual(said.map((s) => s.text), ["walk_forward"]);
});

// T9: speaking rules

test("T9 a static scene is spoken once", () => {
  const { server, said, advance } = setup();
  for (let i = 0; i < 120; i++) {      // a minute at 2 results per second
    server("walk_forward");
    advance(500);
  }
  assert.equal(said.length, 1);
});

test("T9 never more than 15 messages a minute", () => {
  const { server, said, advance } = setup();
  const commands = ["walk_forward", "slow_down", "walk_forward_slow", "yield"];
  for (let i = 0; i < 120; i++) {
    server(commands[i % commands.length]);
    advance(500);
  }
  assert.ok(said.length <= 15, `${said.length} messages`);
  assert.ok(said.length >= 14);
});

test("T9 a stop is never held back by the rate limit", () => {
  const { server, said, advance } = setup();
  const commands = ["walk_forward", "slow_down"];
  for (let i = 0; i < 15; i++) { server(commands[i % 2]); advance(100); }
  assert.equal(server("stop"), "spoken");
  assert.equal(said.at(-1).interrupt, true);
});

test("T9 only a stop interrupts speech", () => {
  const { server, said } = setup();
  server("walk_forward");
  server("slow_down");
  server("stop");
  assert.deepEqual(said.map((s) => s.interrupt), [false, false, true]);
});

test("T9 steps cannot alternate faster than every 2 s", () => {
  const { server, said, advance } = setup();
  assert.equal(server("step_left"), "spoken");
  advance(800);
  assert.equal(server("step_right"), "rate_limited");
  advance(1300);
  assert.equal(server("step_right"), "spoken");
  assert.deepEqual(said.map((s) => s.text), ["step_left", "step_right"]);
});

test("detail is spoken for hazards at normal verbosity, always when detailed, never when brief", () => {
  const { g, server, said } = setup();
  server("yield", { detail: "cyclist crossing from your left, 4 metres" });
  server("step_right", { detail: "opening on your right" });
  g.verbosity = "detailed";
  server("walk_forward", { detail: "path clear" });
  g.verbosity = "brief";
  server("stop", { detail: "person ahead, 1 metres" });
  assert.deepEqual(said.map((s) => s.text), [
    "yield. cyclist crossing from your left, 4 metres",
    "step_right",
    "walk_forward. path clear",
    "stop",
  ]);
});

test("muting silences guidance; the current command is spoken again on unmute", () => {
  const { g, server, said, vibrations } = setup();
  g.muted = true;
  assert.equal(server("yield"), "muted");
  assert.equal(vibrations.length, 1);
  g.muted = false;
  assert.equal(server("yield"), "spoken");
  assert.equal(said.length, 1);
});
