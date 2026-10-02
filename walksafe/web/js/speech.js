// What the user hears and feels: a short sound per command (Web Audio), then
// speech (speechSynthesis), plus vibration where the browser has it.

// Frequencies (Hz) and durations (s) of each command's earcon.
const EARCONS = {
  stop:              [[880, 0.08], [880, 0.08]],
  yield:             [[660, 0.15]],
  slow_down:         [[520, 0.12], [440, 0.12]],
  walk_forward_slow: [[440, 0.08], [520, 0.08]],
  step_left:         [[392, 0.08], [330, 0.08]],
  step_right:        [[330, 0.08], [392, 0.08]],
  turn_left:         [[392, 0.08], [294, 0.14]],
  turn_right:        [[294, 0.08], [392, 0.14]],
  walk_forward:      [[523, 0.07], [659, 0.07]],
  announce:          [[300, 0.2]],
};

export class Speaker {
  constructor() {
    this.ctx = null;
    this.rate = 1;
    this.pending = null;
  }

  // Browsers only allow audio after a user gesture, so call this from one.
  unlock() {
    this.ctx ??= new AudioContext();
    this.ctx.resume();
    speechSynthesis.speak(new SpeechSynthesisUtterance(""));
  }

  earcon(name) {
    const tones = EARCONS[name];
    if (!this.ctx || !tones) return 0;
    let t = this.ctx.currentTime;
    for (const [freq, dur] of tones) {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.4, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
      osc.connect(gain).connect(this.ctx.destination);
      osc.start(t);
      osc.stop(t + dur);
      t += dur + 0.02;
    }
    return t - this.ctx.currentTime;
  }

  // Speech starts `after` seconds from now, once the earcon has played. A stop
  // cuts off whatever is being said; anything else waits for the current
  // utterance, and only the newest waiting message is kept.
  speak(text, { interrupt = false, after = 0 } = {}) {
    if (interrupt) {
      this.pending = null;
      speechSynthesis.cancel();
      setTimeout(() => this.utter(text), after * 1000);
    } else if (speechSynthesis.speaking || speechSynthesis.pending) {
      this.pending = text;
    } else {
      setTimeout(() => this.utter(text), after * 1000);
    }
  }

  utter(text) {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = this.rate;
    u.onend = () => {
      const next = this.pending;
      this.pending = null;
      if (next) this.utter(next);
    };
    speechSynthesis.speak(u);
  }

  vibrate(pattern) {
    navigator.vibrate?.(pattern);      // absent on iOS
  }
}
