// What the user hears. speechSynthesis for words, a short alarm before "stop".
export class Speaker {
  constructor() {
    this.ctx = null;
    this.rate = 1;
    this.pending = null;
  }

  // Browsers allow sound only after a tap; call this from the tap handler.
  unlock() {
    try {
      this.ctx ??= new AudioContext();
      this.ctx.resume();
    } catch { /* no Web Audio */ }
  }

  // interrupt: cut off whatever is being said. Otherwise wait for it, keeping
  // only the newest waiting message.
  say(text, { interrupt = false } = {}) {
    if (!text) return;
    if (interrupt) {
      this.pending = null;
      speechSynthesis.cancel();
      setTimeout(() => this.utter(text), 60);     // Chrome drops a speak() right after cancel()
    } else if (speechSynthesis.speaking || speechSynthesis.pending) {
      this.pending = text;
    } else {
      this.utter(text);
    }
  }

  utter(text) {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = this.rate;
    u.lang = "en-US";
    u.onend = u.onerror = () => {
      const next = this.pending;
      this.pending = null;
      if (next) this.utter(next);
    };
    speechSynthesis.speak(u);
  }

  silence() {
    this.pending = null;
    speechSynthesis.cancel();
  }

  alarm() {
    if (!this.ctx) return;
    let t = this.ctx.currentTime;
    for (let i = 0; i < 2; i++) {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.4, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.09);
      osc.connect(gain).connect(this.ctx.destination);
      osc.start(t);
      osc.stop(t + 0.09);
      t += 0.12;
    }
  }
}
