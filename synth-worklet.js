// Real-time StyloSynth-555 voice. Parameters come from synth-model.js deriveParams() via the port.

function f555(rc, vc, vdd) {
  const v = Math.min(Math.max(vc, 0.2), vdd - 0.05);
  return 1 / (rc * (Math.log((vdd - v / 2) / (vdd - v)) + Math.LN2));
}

// polynomial band-limited step: removes most aliasing from the hard 4040 edges
function blep(t, dt) {
  if (t < dt) {
    t /= dt;
    return t + t - t * t - 1;
  }
  if (t > 1 - dt) {
    t = (t - 1) / dt;
    return t * t + t + t + 1;
  }
  return 0;
}

class StyloSynthProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const init = options?.processorOptions || {};
    this.p = init.params || null;
    this.master = typeof init.master === "number" ? init.master : 0.5;
    this.phase = 0;
    this.held = 1;
    this.lfoV = 2.25;
    this.lfoHigh = true;
    this.tone = 0;
    this.vc11 = 0;
    this.hp = 0;
    this.prevIn = 0;
    this.gain = 0;
    this.port.onmessage = (e) => {
      if (e.data.params) this.p = e.data.params;
      if (typeof e.data.master === "number") this.master = e.data.master;
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0];
    const left = out[0];
    const p = this.p;
    if (!p) {
      for (const ch of out) ch.fill(0);
      return true;
    }
    const dt = 1 / sampleRate;
    const aLfo = 1 - Math.exp(-dt / p.lfo.rc);
    const lMid = (p.lfo.thHi + p.lfo.thLo) / 2,
      lHalf = (p.lfo.thHi - p.lfo.thLo) / 2;
    const aOut = p.rcOut / (p.rcOut + dt);
    const lim = Math.max(0.42 * p.v9, 0.05); // LM386 swing about its Vs/2 bias
    const target = p.power ? 1 : 0;
    for (let i = 0; i < left.length; i++) {
      this.gain += (target - this.gain) * 0.002;
      if (p.power) {
        this.lfoV +=
          ((this.lfoHigh ? p.lfo.outHi : p.lfo.outLo) - this.lfoV) * aLfo;
        if (this.lfoHigh && this.lfoV >= p.lfo.thHi) this.lfoHigh = false;
        else if (!this.lfoHigh && this.lfoV <= p.lfo.thLo) this.lfoHigh = true;
      }
      let y;
      if (p.power && p.active) {
        const vc = p.vc0 + (p.cvDev * (this.lfoV - lMid)) / lHalf;
        const inc = Math.min(
          (p.kcal * f555(p.rc, vc, p.vdd)) / p.divide / sampleRate,
          0.5,
        );
        this.phase += inc;
        if (this.phase >= 1) this.phase -= 1;
        this.held = this.phase < 0.5 ? 1 : 0;
        y =
          this.held +
          0.5 * blep(this.phase, inc) -
          0.5 * blep((this.phase + 0.5) % 1, inc);
      } else {
        // stylus lifted: the 555 parks high and the counter holds its last output level
        y = p.power ? this.held : 0;
      }
      const src = p.vdd * y;
      let t;
      if (p.toneSoft) {
        t = this.tone;
        const iLoad = (t - this.vc11) / p.rLoad;
        this.tone += (dt * ((src - t) / p.rSrc - iLoad)) / p.cTone;
        this.vc11 += (dt * iLoad) / p.cCouple;
      } else {
        t = (src * p.rLoad + this.vc11 * p.rSrc) / (p.rSrc + p.rLoad);
        this.tone = t;
        this.vc11 += (dt * (t - this.vc11)) / p.rLoad / p.cCouple;
      }
      const v = p.gain * (t - this.vc11) * p.kAmp;
      const clipped =
        (lim * v) / Math.pow(1 + Math.pow(Math.abs(v / lim), 6), 1 / 6);
      this.hp = aOut * (this.hp + clipped - this.prevIn);
      this.prevIn = clipped;
      // 4 V at the speaker = digital full scale
      const s = this.hp * p.outScale * 0.25 * this.master * this.gain;
      left[i] = s > 1 ? 1 : s < -1 ? -1 : s;
    }
    for (let c = 1; c < out.length; c++) out[c].set(left);
    return true;
  }
}

registerProcessor("stylosynth", StyloSynthProcessor);
