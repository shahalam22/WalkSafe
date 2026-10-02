import assert from "node:assert/strict";
import { test } from "node:test";

import { ExpansionCheck, blockFlow, timeToContact } from "../../walksafe/web/js/expansion.js";

const CFG = {
  expansion_block_px: 3, expansion_search_px: 4, expansion_grid_px: 6, expansion_min_texture: 60,
  expansion_min_points: 20, expansion_region_left: 0.2, expansion_region_right: 0.8,
  expansion_region_top: 0.15, expansion_region_bottom: 0.7, expansion_max_gap_ms: 300,
  ttc_stop_s: 1.5, ttc_clear_s: 2.5, stop_frames: 3, clear_frames: 5,
};
const W = 96, H = 72, DT = 1000 / 12;

// A continuous texture, so scaled and shifted views of it are exact.
function texture(x, y) {
  return 128 + 45 * Math.sin(x * 0.61 + 1.3 * Math.sin(y * 0.23))
             + 35 * Math.sin(y * 0.53 + 0.7 * Math.cos(x * 0.31))
             + 20 * Math.sin((x + y) * 0.37);
}

// The view after the scene has grown by `scale` about (cx, cy) and moved by (shiftX, shiftY).
function view({ scale = 1, shiftX = 0, shiftY = 0, cx = W / 2, cy = H / 2, flat = false }) {
  const g = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const sx = (x - cx - shiftX) / scale + cx, sy = (y - cy - shiftY) / scale + cy;
      g[y * W + x] = flat ? 128 : Math.max(0, Math.min(255, Math.round(texture(sx, sy))));
    }
  }
  return g;
}

// Feeds n frames growing by `growth` per frame (and shifting by `shift` px per frame).
function run(n, { growth = 1, shift = 0, cx, flat } = {}) {
  const check = new ExpansionCheck(CFG);
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push(check.update(view({ scale: growth ** i, shiftX: shift * i, cx, flat }), W, H, i * DT));
  }
  return out;
}

test("block matching recovers a pure shift", () => {
  const flow = blockFlow(view({}), view({ shiftX: 2, shiftY: -1 }), W, H, CFG);
  assert.ok(flow.length > 50);
  const mu = flow.reduce((s, p) => s + p.u, 0) / flow.length;
  const mv = flow.reduce((s, p) => s + p.v, 0) / flow.length;
  assert.ok(Math.abs(mu - 2) < 0.15 && Math.abs(mv + 1) < 0.15, `${mu}, ${mv}`);
});

test("time to contact from a known expansion", () => {
  // Growing 5 % a frame at 12 fps: TTC = (1/12) / 0.05 = 1.67 s.
  const flow = blockFlow(view({}), view({ scale: 1.05 }), W, H, CFG);
  const ttc = timeToContact(flow, 1 / 12);
  assert.ok(Math.abs(ttc - 1.67) < 0.25, `ttc ${ttc}`);
});

test("something closing fast triggers a stop after three frames", () => {
  const out = run(6, { growth: 1.08 });           // TTC about 1.0 s
  assert.deepEqual(out.map((r) => r.stop), [false, false, false, true, true, true]);
  assert.ok(out[3].ttc < 1.5);
});

test("the stop holds until the scene stops closing, then clears", () => {
  const check = new ExpansionCheck(CFG);
  let i = 0, scale = 1;
  const step = (growth) => { scale *= growth; return check.update(view({ scale }), W, H, i++ * DT); };
  for (let k = 0; k < 5; k++) step(1.08);
  assert.equal(step(1.08).stop, true);
  const after = [];
  for (let k = 0; k < 6; k++) after.push(step(1.0).stop);
  assert.deepEqual(after, [true, true, true, true, false, false]);
});

test("walking toward something far away does not stop", () => {
  const out = run(10, { growth: 1.01 });         // TTC about 8 s
  assert.ok(out.every((r) => !r.stop));
});

test("sideways motion and an off-centre point of expansion are not mistaken for closing in", () => {
  assert.ok(run(10, { shift: 2 }).every((r) => !r.stop));
  const offCentre = run(6, { growth: 1.08, cx: W * 0.35 });
  assert.equal(offCentre.at(-1).stop, true);
});

test("a covered camera or a blank view reports the check as unavailable", () => {
  const out = run(3, { flat: true });
  assert.equal(out[2].available, false);
});

test("frames too far apart are not compared", () => {
  const check = new ExpansionCheck(CFG);
  check.update(view({}), W, H, 0);
  const r = check.update(view({ scale: 1.3 }), W, H, 1000);
  assert.equal(r.ttc, null);
});

test("NFR-3: one update takes well under 100 ms (desktop Node, not a phone measurement)", () => {
  const check = new ExpansionCheck(CFG);
  const frames = [view({}), view({ scale: 1.02 })];
  check.update(frames[0], W, H, 0);
  const t0 = performance.now();
  for (let i = 1; i <= 50; i++) check.update(frames[i % 2], W, H, i * DT);
  const ms = (performance.now() - t0) / 50;
  console.log(`expansion check: ${ms.toFixed(2)} ms per frame`);
  assert.ok(ms < 20);
});
