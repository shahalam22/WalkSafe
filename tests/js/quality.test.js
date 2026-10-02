import assert from "node:assert/strict";
import { test } from "node:test";

import { brightness, checkFrame, sharpness } from "../../walksafe/web/js/quality.js";

const CFG = { dark_max: 40, bright_min: 215, blur_min: 30 };
const W = 96, H = 72;

function frame(fn) {
  const g = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) g[y * W + x] = fn(x, y);
  return g;
}

const checker = frame((x, y) => ((x >> 2) + (y >> 2)) % 2 ? 200 : 60);

test("a textured frame is usable", () => {
  assert.equal(checkFrame(checker, W, H, CFG).ok, true);
});

test("dark, bright and flat frames are rejected with the cause", () => {
  assert.equal(checkFrame(frame(() => 10), W, H, CFG).cause, "dark");
  assert.equal(checkFrame(frame(() => 240), W, H, CFG).cause, "bright");
  assert.equal(checkFrame(frame(() => 128), W, H, CFG).cause, "blur");
});

test("brightness and sharpness", () => {
  assert.equal(brightness(frame(() => 100)), 100);
  assert.equal(sharpness(frame(() => 100), W, H), 0);
  assert.ok(sharpness(checker, W, H) > 1000);
});
