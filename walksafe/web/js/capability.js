// Capability levels (SRS §2.2, FR-18 to FR-20). Each fault reports whether it
// is present; the level is the most severe active one. Every change is
// announced with its cause and logged, a reduced level is repeated every
// minute, and recovery is announced. No browser APIs here.

export const LEVELS = ["L0", "L1", "L2", "L3", "L4"];

const worse = (a, b) => (LEVELS.indexOf(a) >= LEVELS.indexOf(b) ? a : b);

export function message(level, cause, previous) {
  switch (level) {
    case "L0": return previous ? "Full guidance restored." : "Full guidance.";
    case "L1": return `Reduced confidence: ${cause}. Cautious guidance only.`;
    case "L2": return `Route guidance lost: ${cause}. Obstacle warnings only.`;
    case "L3": return `Guidance stopped: ${cause}.`;
    default:   return `WalkSafe is shutting down: ${cause}.`;
  }
}

export class Capability {
  constructor({ announce, now, cfg, onEvent = () => {} }) {
    this.announce = announce;
    this.now = now;
    this.cfg = cfg;
    this.onEvent = onEvent;
    this.level = null;              // unknown until the server answers or is overdue
    this.cause = "";
    this.lastAnnounced = 0;
    this.faults = new Map();
    this.pendingSince = null;       // oldest request the server has not answered
    this.lastCheck = now();
    this.batteryWarned = new Set();
  }

  // Called with the current state of a fault each time it is checked.
  report(name, active, level, cause, onsetMs = this.cfg.fault_onset_ms) {
    const now = this.now();
    const f = this.faults.get(name) ?? { on: false, onset: null, gone: null };
    Object.assign(f, { level, cause });
    if (active) {
      f.gone = null;
      f.onset ??= now;
      if (now - f.onset >= onsetMs) f.on = true;
    } else {
      f.onset = null;
      if (f.on) {
        f.gone ??= now;
        if (now - f.gone >= this.cfg.fault_clear_ms) f.on = false;
      }
    }
    this.faults.set(name, f);
  }

  requestSent() {
    this.pendingSince ??= this.now();
  }

  serverAnswered(serverLevel) {
    this.pendingSince = null;
    this.report("server_view", serverLevel === "L1", "L1", "the server is unsure of the view");
  }

  checkRan(result) {
    this.lastCheck = this.now();
    this.report("expansion", !result.available, "L3", "the camera view is blocked or too plain to check",
                this.cfg.expansion_unavailable_ms);
  }

  battery(level, charging) {
    if (charging) { this.batteryWarned.clear(); return; }
    for (const warn of this.cfg.battery_warn_levels) {
      if (level <= warn && !this.batteryWarned.has(warn)) {
        this.batteryWarned.add(warn);
        const pct = Math.round(level * 100);
        this.announce(`Battery at ${pct} percent.`, { urgent: false });
        this.onEvent({ type: "battery", occurred_at: this.now(), cause: `battery_${pct}` });
      }
    }
    if (level <= this.cfg.battery_end_level) this.end("battery nearly empty");
  }

  end(cause) {
    this.report("end", true, "L4", cause, 0);
    this.tick();
  }

  tick() {
    const now = this.now();
    const silent = this.pendingSince !== null && now - this.pendingSince > this.cfg.server_silent_ms;
    this.report("server", silent, "L2", "the server is not answering in time", 0);
    this.report("check", now - this.lastCheck > this.cfg.check_dead_ms, "L3", "the obstacle check stopped", 0);

    let level = "L0", cause = "";
    for (const f of this.faults.values()) {
      if (f.on && worse(f.level, level) === f.level && f.level !== level) { level = f.level; cause = f.cause; }
    }
    if (this.level === null && level === "L0" && this.pendingSince !== null) return;   // still waiting

    if (level !== this.level) {
      const from = this.level;
      this.level = level;
      this.cause = cause;
      this.lastAnnounced = now;
      this.announce(message(level, cause, from), { urgent: level >= "L2" });
      this.onEvent({ type: "level_change", occurred_at: now, cause: cause || "recovered",
                     from_level: from, to_level: level });
    } else if (level !== "L0" && level !== "L4" && now - this.lastAnnounced >= this.cfg.announce_repeat_ms) {
      this.lastAnnounced = now;
      this.announce(message(level, cause, level), { urgent: false });
    }
  }
}
