// Guidance control (FR-12 to FR-17): a stop from the phone always wins, old or
// out-of-order server results are dropped, and only a change of command is
// spoken, within the rate limits. Output and clock are passed in, so nothing
// here touches the browser.

const URGENT = new Set(["stop", "yield"]);
const HAZARD = new Set(["stop", "yield", "slow_down"]);

export const VIBRATION = {
  stop:  [200, 100, 200, 100, 200],
  yield: [300],
};

export class Guidance {
  constructor({ output, now, cfg, onDelivery = () => {} }) {
    this.output = output;
    this.now = now;
    this.cfg = cfg;
    this.onDelivery = onDelivery;
    this.muted = false;
    this.verbosity = "normal";      // brief | normal | detailed
    this.lastSeq = -1;
    this.lastSpoken = null;
    this.lastStepAt = -Infinity;
    this.spokenAt = [];
    this.phoneStopActive = false;
    this.phoneClearedAt = -Infinity;
  }

  // The expansion check sees something closing in. Kept to one word: it has
  // to reach the user within 250 ms (NFR-1).
  phoneStop() {
    if (this.phoneStopActive) return;
    this.phoneStopActive = true;
    this.say("stop", "Stop", true);
  }

  // Results captured before this moment describe the scene during the stop,
  // so they are not trusted afterwards.
  phoneClear() {
    if (!this.phoneStopActive) return;
    this.phoneStopActive = false;
    this.phoneClearedAt = this.now();
  }

  serverResult(r) {
    const outcome = this.judge(r);
    if (outcome === "spoken") this.say(r.command, this.text(r.phrase, r.detail, r.command));
    else if (outcome === "muted" && URGENT.has(r.command)) this.output.vibrate(VIBRATION[r.command]);
    this.onDelivery({ seq: r.seq, outcome, spoken_at: outcome === "spoken" ? this.now() : null });
    return outcome;
  }

  judge(r) {
    const now = this.now();
    if (r.seq <= this.lastSeq) return "out_of_order";
    this.lastSeq = r.seq;
    if (now - r.capture_ts > this.cfg.stale_after_ms) return "stale";
    if (this.phoneStopActive || r.capture_ts < this.phoneClearedAt) return "overridden";
    if (r.command === this.lastSpoken) return "repeat";
    if (this.muted) return "muted";
    // A stop is never held back by the rate limits.
    if (r.command !== "stop") {
      const recent = this.spokenAt.filter((t) => now - t < 60_000).length;
      if (recent >= this.cfg.max_messages_per_min) return "rate_limited";
      if (r.command.startsWith("step_") && now - this.lastStepAt < this.cfg.step_min_interval_ms) {
        return "rate_limited";
      }
    }
    return "spoken";
  }

  text(phrase, detail, command) {
    if (!detail || this.verbosity === "brief") return phrase;
    if (this.verbosity === "normal" && !HAZARD.has(command)) return phrase;
    return `${phrase}. ${detail}`;
  }

  say(command, text, fromPhone = false) {
    const now = this.now();
    if (URGENT.has(command)) this.output.vibrate(VIBRATION[command]);
    if (this.muted) return;
    const after = this.output.earcon(command);
    this.output.speak(text, { interrupt: command === "stop", after });
    this.lastSpoken = command;
    this.spokenAt = this.spokenAt.filter((t) => now - t < 60_000).concat(now);
    if (command.startsWith("step_")) this.lastStepAt = now;
    if (fromPhone) this.onDelivery({ seq: null, outcome: "phone_stop", spoken_at: now });
  }
}
