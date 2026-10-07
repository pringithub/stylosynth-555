// Pedalboard after the synth: phaser -> delay -> reverb -> limiter (plain Web Audio nodes).

export const PEDALS = [
  {
    id: "phaser",
    name: "PHASER",
    color: "#9575cd",
    about:
      "Sweeps notches through the spectrum with a chain of all-pass filters moved by a slow LFO: the classic swirl.",
    params: [
      {
        id: "rate",
        label: "Rate",
        min: 0.05,
        max: 6,
        step: 0.01,
        fmt: (v) => `${v.toFixed(2)} Hz`,
      },
      { id: "depth", label: "Depth", min: 0, max: 1, step: 0.01, fmt: pctFmt },
      { id: "res", label: "Res", min: 0, max: 1, step: 0.01, fmt: pctFmt },
      { id: "mix", label: "Mix", min: 0, max: 1, step: 0.01, fmt: pctFmt },
    ],
  },
  {
    id: "delay",
    name: "DELAY",
    color: "#4db6ac",
    about:
      "Ping-pong echo: repeats bounce between left and right. Feedback gives more echoes, tone darkens each " +
      "repeat like tape, width spreads them across the stereo field.",
    params: [
      {
        id: "time",
        label: "Time",
        min: 0.03,
        max: 5,
        step: 0.01,
        fmt: (v) => `${Math.round(v * 1000)} ms`,
      },
      {
        id: "feedback",
        label: "Fdbk",
        min: 0,
        max: 0.9,
        step: 0.01,
        fmt: pctFmt,
      },
      { id: "tone", label: "Tone", min: 0, max: 1, step: 0.01, fmt: pctFmt },
      { id: "width", label: "Width", min: 0, max: 1, step: 0.01, fmt: pctFmt },
      { id: "mix", label: "Mix", min: 0, max: 1, step: 0.01, fmt: pctFmt },
    ],
  },
  {
    id: "reverb",
    name: "REVERB",
    color: "#64b5f6",
    about:
      "Simulated room: a decaying noise impulse response convolved with the signal.",
    params: [
      {
        id: "decay",
        label: "Decay",
        min: 0.3,
        max: 8,
        step: 0.1,
        fmt: (v) => `${v.toFixed(1)} s`,
      },
      { id: "tone", label: "Tone", min: 0, max: 1, step: 0.01, fmt: pctFmt },
      { id: "mix", label: "Mix", min: 0, max: 1, step: 0.01, fmt: pctFmt },
    ],
  },
];

export const PEDAL_DEFAULTS = {
  phaser: { on: false, rate: 0.4, depth: 0.8, res: 0.4, mix: 0.7 },
  delay: {
    on: false,
    time: 0.36,
    feedback: 0.4,
    tone: 0.6,
    width: 0.7,
    mix: 0.35,
  },
  reverb: { on: false, decay: 2.5, tone: 0.6, mix: 0.3 },
};

function pctFmt(v) {
  return `${Math.round(v * 100)} %`;
}

const SMOOTH = 0.03; // s, time constant for parameter moves (avoids zipper noise and clicks)
const BYPASS = 0.008; // s, faster time constant for switching a pedal in or out
const PHASER_STAGES = 6;
const PHASER_CENTER = 800; // Hz

export class PedalBoard {
  constructor(ctx, input, state, trails = false) {
    this.ctx = ctx;
    this.state = structuredClone(state);
    this.trails = trails;
    const g = (v = 1) => {
      const n = ctx.createGain();
      n.gain.value = v;
      return n;
    };

    // phaser: dry + all-pass chain (sum produces the notches)
    this.phIn = g();
    this.phOut = g();
    this.phWet = g(0);
    this.allpass = Array.from({ length: PHASER_STAGES }, () => {
      const f = ctx.createBiquadFilter();
      f.type = "allpass";
      f.frequency.value = PHASER_CENTER;
      return f;
    });
    this.lfo = ctx.createOscillator();
    this.lfoDepth = g(0);
    this.lfo.connect(this.lfoDepth);
    this.allpass.forEach((f, i) => {
      this.lfoDepth.connect(f.frequency);
      if (i) this.allpass[i - 1].connect(f);
    });
    this.lfo.start();
    this.phIn.connect(this.phOut);
    this.phIn.connect(this.allpass[0]);
    this.allpass.at(-1).connect(this.phWet).connect(this.phOut);

    // delay: send gate (so echoes ring out after switching off) -> two cross-fed lines (ping-pong)
    this.dlSend = g(0);
    this.dlWet = g(0);
    this.dlOut = g();
    this.dlTaps = [-1, 1].map((side) => {
      const line = ctx.createDelay(5);
      const tone = ctx.createBiquadFilter();
      tone.type = "lowpass";
      const fb = g(0);
      const pan = ctx.createStereoPanner();
      line.connect(tone);
      tone.connect(fb);
      tone.connect(pan).connect(this.dlWet);
      return { side, line, tone, fb, pan };
    });
    const [tapA, tapB] = this.dlTaps;
    tapA.fb.connect(tapB.line);
    tapB.fb.connect(tapA.line);
    this.phOut.connect(this.dlOut);
    this.phOut.connect(this.dlSend).connect(tapA.line);
    this.dlWet.connect(this.dlOut);

    // reverb: send gate -> convolver (generated impulse) -> tone -> wet
    this.rvSend = g(0);
    this.rvConv = ctx.createConvolver();
    this.rvTone = ctx.createBiquadFilter();
    this.rvTone.type = "lowpass";
    this.rvWet = g(0);
    this.rvOut = g();
    this.dlOut.connect(this.rvOut);
    this.dlOut
      .connect(this.rvSend)
      .connect(this.rvConv)
      .connect(this.rvTone)
      .connect(this.rvWet)
      .connect(this.rvOut);

    // limiter so stacked echoes and reverb can't clip the output
    this.limiter = ctx.createDynamicsCompressor();
    this.limiter.threshold.value = -4;
    this.limiter.knee.value = 3;
    this.limiter.ratio.value = 20;
    this.limiter.attack.value = 0.003;
    this.limiter.release.value = 0.15;
    this.rvOut.connect(this.limiter);
    this.output = this.limiter;

    input.connect(this.phIn);
    this.irDecay = null;
    this.applyAll();
  }

  ramp(param, value, tc = SMOOTH) {
    param.setTargetAtTime(value, this.ctx.currentTime, tc);
  }

  applyAll() {
    for (const p of PEDALS) this.apply(p.id);
  }

  /** Trails on: switching delay/reverb off only stops new input, so echoes and tails ring out. */
  setTrails(on) {
    this.trails = on;
    this.applyAll();
  }

  apply(pedal) {
    const s = this.state[pedal];
    const live = s.on || this.trails;
    if (pedal === "phaser") {
      this.ramp(this.lfo.frequency, s.rate);
      this.ramp(this.lfoDepth.gain, PHASER_CENTER * 0.9 * s.depth);
      for (const f of this.allpass) this.ramp(f.Q, 0.4 + 6 * s.res * s.res);
      this.ramp(this.phWet.gain, s.on ? s.mix : 0, BYPASS);
    } else if (pedal === "delay") {
      for (const t of this.dlTaps) {
        this.ramp(t.line.delayTime, s.time);
        // with trails off, killing the feedback drains the lines so old echoes can't come back later
        this.ramp(t.fb.gain, live ? s.feedback : 0, BYPASS);
        this.ramp(t.tone.frequency, 800 * 2 ** (s.tone * 4));
        this.ramp(t.pan.pan, t.side * s.width);
      }
      this.ramp(this.dlWet.gain, live ? s.mix : 0, BYPASS);
      this.ramp(this.dlSend.gain, s.on ? 1 : 0, BYPASS);
    } else if (pedal === "reverb") {
      if (this.irDecay !== s.decay) this.scheduleImpulse(s.decay);
      this.ramp(this.rvTone.frequency, 1200 * 2 ** (s.tone * 4));
      this.ramp(this.rvWet.gain, live ? s.mix * 1.6 : 0, BYPASS);
      this.ramp(this.rvSend.gain, s.on ? 1 : 0, BYPASS);
    }
  }

  set(pedal, param, value) {
    this.state[pedal][param] = value;
    this.apply(pedal);
  }

  dispose() {
    clearTimeout(this.irTimer);
    this.lfo.stop();
    this.output.disconnect();
  }

  load(state) {
    this.state = structuredClone(state);
    this.applyAll();
  }

  scheduleImpulse(decay) {
    this.irDecay = decay;
    clearTimeout(this.irTimer);
    // regenerating the impulse is relatively costly; wait until a knob drag settles
    this.irTimer = setTimeout(
      () => {
        this.rvConv.buffer = makeImpulse(this.ctx, decay);
      },
      this.rvConv.buffer ? 150 : 0,
    );
  }
}

/** Stereo exponentially-decaying noise (RT60 = decay) with a short pre-delay. */
function makeImpulse(ctx, decay) {
  const rate = ctx.sampleRate;
  const pre = Math.round(0.012 * rate);
  const len = pre + Math.round(decay * rate);
  const buf = ctx.createBuffer(2, len, rate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = pre; i < len; i++) {
      const t = (i - pre) / rate;
      d[i] = (Math.random() * 2 - 1) * Math.exp((-6.9 * t) / decay);
    }
  }
  return buf;
}
