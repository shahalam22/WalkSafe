// Talking to the server. One frame in flight at a time, always the newest.

export class ApiError extends Error {
  constructor(status, detail) {
    super(`${status} ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

export class Api {
  constructor(base = "", { fetchFn = globalThis.fetch?.bind(globalThis), timeoutMs = 3000 } = {}) {
    this.base = base;
    this.fetch = fetchFn;
    this.timeoutMs = timeoutMs;
  }

  async request(path, init) {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), this.timeoutMs);
    try {
      const res = await this.fetch(this.base + path, { ...init, signal: abort.signal });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new ApiError(res.status, body.detail ?? body.error ?? "error");
      return body;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(0, abort.signal.aborted ? "timeout" : "network");
    } finally {
      clearTimeout(timer);
    }
  }

  postJson(path, body) {
    return this.request(path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  }

  async startSession(profile, purpose = "walk") {
    return (await this.postJson("/api/session", { purpose, profile })).session_id;
  }

  endSession(sessionId, reason) {
    return this.postJson("/api/session/end", { session_id: sessionId, reason });
  }

  postEvents(sessionId, events) {
    return this.postJson("/api/event", { session_id: sessionId, events });
  }

  sendFrame(sessionId, seq, captureTs, blob) {
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("seq", String(seq));
    form.append("capture_ts", String(captureTs));
    form.append("image", blob, "frame.jpg");
    return this.request("/api/frame", { method: "POST", body: form });
  }
}

// Sends frames one after another until stopped. grab() is called only when the
// previous request has finished, so whatever goes out is the newest frame.
export async function uploadLoop({ api, sessionId, grab, onResult, onError, running,
                                   onSent = () => {}, retryMs = 1000 }) {
  let seq = 0;
  while (running()) {
    const frame = await grab();
    if (!frame) { await sleep(100); continue; }
    onSent();
    try {
      onResult(await api.sendFrame(sessionId, ++seq, frame.ts, frame.blob));
    } catch (e) {
      onError(e);
      if (e.status === 404) return;            // session gone; the caller starts a new one
      await sleep(retryMs);
    }
  }
}

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
