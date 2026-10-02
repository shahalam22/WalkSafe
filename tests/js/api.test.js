import assert from "node:assert/strict";
import { test } from "node:test";

import { Api, ApiError, uploadLoop } from "../../walksafe/web/js/api.js";

const reply = (status, body) => Promise.resolve({ ok: status < 400, status, json: async () => body });

test("only one frame is in flight and each one is grabbed when the last finishes", async () => {
  let inFlight = 0, maxInFlight = 0, grabbed = 0;
  const fetchFn = async () => {
    inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise((r) => setTimeout(r, 5));
    inFlight--;
    return reply(200, { command: "walk_forward" });
  };
  const results = [];
  await uploadLoop({
    api: new Api("", { fetchFn }), sessionId: "s",
    grab: async () => ({ blob: new Blob(["x"]), ts: ++grabbed }),
    onResult: (r) => results.push(r), onError: () => {},
    running: () => results.length < 5,
  });
  assert.equal(maxInFlight, 1);
  assert.equal(grabbed, 5);
});

test("sequence numbers increase and capture times are sent", async () => {
  const sent = [];
  const fetchFn = async (url, init) => {
    sent.push([init.body.get("seq"), init.body.get("capture_ts")]);
    return reply(200, {});
  };
  let n = 0;
  await uploadLoop({
    api: new Api("", { fetchFn }), sessionId: "s",
    grab: async () => ({ blob: new Blob(["x"]), ts: 1000 + n }),
    onResult: () => n++, onError: () => {}, running: () => n < 3,
  });
  assert.deepEqual(sent, [["1", "1000"], ["2", "1001"], ["3", "1002"]]);
});

test("errors are reported and retried; a lost session ends the loop", async () => {
  const statuses = [0, 500, 200, 404];
  const fetchFn = async () => {
    const s = statuses.shift();
    if (s === 0) throw new TypeError("Failed to fetch");
    return reply(s, s === 404 ? { detail: "unknown_session" } : {});
  };
  const errors = [], results = [];
  await uploadLoop({
    api: new Api("", { fetchFn }), sessionId: "s", retryMs: 1,
    grab: async () => ({ blob: new Blob(["x"]), ts: 1 }),
    onResult: (r) => results.push(r), onError: (e) => errors.push(e.status), running: () => true,
  });
  assert.deepEqual(errors, [0, 500, 404]);
  assert.equal(results.length, 1);
});

test("a request that takes too long times out", async () => {
  const fetchFn = (url, init) => new Promise((_, reject) =>
    init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
  const api = new Api("", { fetchFn, timeoutMs: 10 });
  await assert.rejects(api.startSession({}), (e) => e instanceof ApiError && e.detail === "timeout");
});

test("session start sends the profile and returns the id", async () => {
  let body;
  const fetchFn = async (url, init) => { body = JSON.parse(init.body); return reply(200, { session_id: "abc" }); };
  const id = await new Api("https://x", { fetchFn }).startSession({ consent_send_images: true });
  assert.equal(id, "abc");
  assert.deepEqual(body, { purpose: "walk", profile: { consent_send_images: true } });
});
