// Spoken setup (FR-23): limits, consent, how the phone is held, the camera's
// field of view, a depth check against a known distance, a left/right test and
// shoulder width. Every step is spoken and answered with ordinary buttons, so
// it works with a screen reader and without sight. A failed depth check or a
// reversed direction test blocks use (NFR-6). The browser parts are passed in.

export class SetupRejected extends Error {}

const LIMITS =
  "WalkSafe warns about people, vehicles and obstacles one to eight metres ahead. " +
  "It does not replace your cane or guide dog, and it cannot detect kerbs, steps or drop-offs. " +
  "Keep using your cane.";
const CONSENT =
  "To analyse the street, WalkSafe sends camera images to its server. Images are never stored. " +
  "Allow this? Without it, WalkSafe only warns when something is about to hit you.";
const MOUNT = "Where will you hold the phone while walking?";
const DISTANCE = "Stand facing a flat wall. How far from it are you? Your cane's length is a good measure.";
const FACE_WALL = "Hold the phone at chest height, pointing at the wall. Press Ready and keep still.";
const STEP_LEFT = "Now the direction test. Hold the phone pointing ahead. After the tone, take one step to your left.";
const SHOULDERS = "Last question: how broad are your shoulders?";

export async function runSetup(ctx) {
  const { ask, say, cfg } = ctx;
  const p = { ...ctx.base, depth_check_passed: false, direction_test_passed: false };

  await ask(LIMITS, [{ key: "ok", label: "I understand" }]);
  p.consent_send_images = (await ask(CONSENT, [
    { key: "yes", label: "Allow" }, { key: "no", label: "Phone only" },
  ])) === "yes";

  const mount = await ask(MOUNT, [{ key: "chest", label: "Chest strap" }, { key: "hand", label: "In my hand" }]);
  p.mount_height_m = mount === "chest" ? cfg.mount_chest_m : cfg.mount_hand_m;
  p.mount_pitch_deg = await aimCheck(ctx);

  if (!p.consent_send_images) {
    say("Setup done. WalkSafe will run on the phone only.");
    return p;
  }

  const sessionId = await ctx.api.startSession(p, "setup");
  try {
    Object.assign(p, await depthCheck(ctx, sessionId));
    p.direction_test_passed = await directionTest(ctx, sessionId);
  } finally {
    ctx.api.endSession(sessionId, "setup").catch(() => {});
  }

  const shoulders = await ask(SHOULDERS, [
    { key: "average", label: "Average" }, { key: "narrow", label: "Narrow" }, { key: "wide", label: "Broad" },
  ]);
  p.shoulder_width_m = cfg[`shoulder_${shoulders}_m`];
  say("Setup done. Press the large button to start guidance.");
  return p;
}

// Pitch is null where the browser gives no orientation; then nothing is checked.
async function aimCheck({ ask, pitch, cfg }) {
  for (let tries = 0; tries < 3; tries++) {
    const deg = await pitch();
    if (deg === null || Math.abs(deg) <= cfg.max_pitch_deg) return deg ?? 0;
    const way = deg < 0 ? "down" : "up";
    await ask(`The phone is pointing ${way}. Hold it upright, pointing straight ahead, then press Ready.`,
              [{ key: "ready", label: "Ready" }]);
  }
  return (await pitch()) ?? 0;
}

async function depthCheck({ ask, say, api, grab }, sessionId) {
  for (;;) {
    const known = Number(await ask(DISTANCE, ["1.5", "1", "2", "3"].map((m) => ({ key: m, label: `${m} metres` }))));
    await ask(FACE_WALL, [{ key: "ready", label: "Ready" }]);
    const frame = await grab();
    const r = await api.depthCheck(sessionId, known, frame.blob);
    if (r.passed) {
      say(`Depth check passed. The wall measured ${r.measured_m} metres.`);
      const result = { depth_check_passed: true, depth_scale: r.depth_scale };
      if (r.fov_deg !== null) result.camera_fov_deg = r.fov_deg;      // otherwise the standard angle
      return result;
    }
    const next = await ask(
      `Depth check failed: the wall measured ${r.measured_m} metres, not ${known}. ` +
      "Make sure you face a flat wall. Try again?",
      [{ key: "retry", label: "Try again" }, { key: "stop", label: "Stop setup" }]);
    if (next === "stop") throw new SetupRejected("the depth check failed");
  }
}

async function directionTest(ctx, sessionId) {
  for (;;) {
    await ctx.ask(STEP_LEFT, [{ key: "ready", label: "Ready" }]);
    ctx.tone();
    const verdict = judgeDirection(await collectActions(ctx, sessionId, ctx.cfg.direction_test_ms));
    if (verdict === "pass") {
      ctx.say("Direction test passed.");
      return true;
    }
    if (verdict === "reversed") {
      throw new SetupRejected("left and right appear reversed on this phone. WalkSafe cannot be used until this is fixed");
    }
    const next = await ctx.ask("The step was not clear. Try again?",
                               [{ key: "retry", label: "Try again" }, { key: "stop", label: "Stop setup" }]);
    if (next === "stop") throw new SetupRejected("the direction test did not pass");
  }
}

export function judgeDirection(actions) {
  const left = actions.includes("stepping_left");
  const right = actions.includes("stepping_right");
  if (left && !right) return "pass";
  if (right && !left) return "reversed";
  return "unclear";
}

// What the server's ego-motion estimate says while the user steps.
export async function collectActions({ api, grab, now, sleep }, sessionId, durationMs) {
  const actions = [];
  const start = now();
  let seq = 0;
  while (now() - start < durationMs) {
    const frame = await grab();
    if (!frame) { await sleep(50); continue; }
    try {
      actions.push((await api.sendFrame(sessionId, ++seq, frame.ts, frame.blob)).ego_action);
    } catch {
      await sleep(200);
    }
  }
  return actions;
}
