import assert from "node:assert/strict";
import { test } from "node:test";

import { judgeDirection, runSetup, SetupRejected } from "../../walksafe/web/js/setup.js";

const CFG = {
  direction_test_ms: 1000, max_pitch_deg: 25, shoulder_narrow_m: 0.38, shoulder_average_m: 0.45,
  shoulder_wide_m: 0.52, mount_chest_m: 1.3, mount_hand_m: 1.1,
};

// Answers are given in order; each question asked is recorded with its choices.
function setup({ answers, egoAction = "stepping_left", depth = { passed: true, measured_m: 1.6, depth_scale: 0.94, fov_deg: 68 },
                 pitches = [0] }) {
  const asked = [], said = [], sent = [];
  const clock = { t: 0 };
  const queue = [...answers];
  const api = {
    startSession: async (profile, purpose) => { sent.push({ profile, purpose }); return "setup-1"; },
    endSession: async () => {},
    depthCheck: async () => (typeof depth === "function" ? depth() : depth),
    sendFrame: async () => { clock.t += 300; return { ego_action: typeof egoAction === "function" ? egoAction() : egoAction }; },
  };
  const ctx = {
    cfg: CFG, api, base: { user_id: "u1", verbosity: "normal" },
    ask: async (q, choices) => {
      asked.push({ q, keys: choices.map((c) => c.key) });
      const a = queue.shift();
      assert.ok(choices.some((c) => c.key === a), `"${a}" is not a choice for: ${q}`);
      return a;
    },
    say: (t) => said.push(t), tone: () => {},
    grab: async () => ({ blob: "jpeg", ts: clock.t }),
    pitch: async () => (pitches.length > 1 ? pitches.shift() : pitches[0]),
    now: () => clock.t, sleep: async () => { clock.t += 50; },
  };
  return { ctx, asked, said, sent };
}

const HAPPY = ["ok", "yes", "chest", "1.5", "ready", "ready", "wide"];

test("a full setup produces the profile the server needs", async () => {
  const { ctx, sent } = setup({ answers: HAPPY });
  const p = await runSetup(ctx);
  assert.deepEqual(p, {
    user_id: "u1", verbosity: "normal", consent_send_images: true,
    mount_height_m: 1.3, mount_pitch_deg: 0, depth_check_passed: true, depth_scale: 0.94,
    camera_fov_deg: 68, direction_test_passed: true, shoulder_width_m: 0.52,
  });
  assert.equal(sent[0].purpose, "setup");
});

test("the limits are stated and acknowledged first, then consent is asked", async () => {
  const { ctx, asked } = setup({ answers: HAPPY });
  await runSetup(ctx);
  assert.match(asked[0].q, /does not replace your cane/);
  assert.match(asked[1].q, /sends camera images/);
});

test("declining consent gives a phone-only profile and sends nothing", async () => {
  const { ctx, sent } = setup({ answers: ["ok", "no", "hand"] });
  const p = await runSetup(ctx);
  assert.equal(p.consent_send_images, false);
  assert.equal(p.mount_height_m, 1.1);
  assert.equal(sent.length, 0);
});

test("T1 a reversed direction test blocks use", async () => {
  // What a build with swapped polarity would report for a step to the left.
  const { ctx } = setup({ answers: HAPPY, egoAction: "stepping_right" });
  await assert.rejects(runSetup(ctx), (e) => e instanceof SetupRejected && /reversed/.test(e.message));
});

test("an unclear step is offered again, and stopping rejects setup", async () => {
  const { ctx } = setup({ answers: ["ok", "yes", "chest", "1.5", "ready", "ready", "stop"],
                          egoAction: "standing_still" });
  await assert.rejects(runSetup(ctx), SetupRejected);
});

test("a failed depth check can be retried", async () => {
  let calls = 0;
  const depth = () => (++calls === 1 ? { passed: false, measured_m: 2.6, depth_scale: 0.58, fov_deg: null }
                                      : { passed: true, measured_m: 1.45, depth_scale: 1.03, fov_deg: null });
  const answers = ["ok", "yes", "chest", "1.5", "ready", "retry", "1.5", "ready", "ready", "average"];
  const { ctx, said } = setup({ answers, depth });
  const p = await runSetup(ctx);
  assert.equal(p.depth_scale, 1.03);
  assert.equal(p.camera_fov_deg, undefined);           // the server's standard angle applies
  assert.ok(said.includes("Depth check passed. The wall measured 1.45 metres."));
});

test("a failed depth check that is not retried rejects setup", async () => {
  const depth = { passed: false, measured_m: 2.6, depth_scale: 0.58, fov_deg: null };
  const { ctx } = setup({ answers: ["ok", "yes", "chest", "1.5", "ready", "stop"], depth });
  await assert.rejects(runSetup(ctx), /depth check failed/);
});

test("a tilted phone is asked to be held level", async () => {
  const { ctx, asked } = setup({ answers: ["ok", "no", "chest", "ready"], pitches: [-40, -5] });
  const p = await runSetup(ctx);
  assert.match(asked[3].q, /pointing down/);
  assert.equal(p.mount_pitch_deg, -5);
});

test("direction verdicts", () => {
  assert.equal(judgeDirection(["standing_still", "stepping_left"]), "pass");
  assert.equal(judgeDirection(["stepping_right"]), "reversed");
  assert.equal(judgeDirection(["stepping_left", "stepping_right"]), "unclear");
  assert.equal(judgeDirection([]), "unclear");
});
