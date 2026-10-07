// Live waveform (triggered scope) and spectrum (FFT) of the synth output.

const F_MIN = 20,
  F_MAX = 20000,
  DB_MIN = -110,
  DB_MAX = -10;

export class SoundViewer {
  constructor(scopeCanvas, fftCanvas, readout) {
    this.scope = scopeCanvas;
    this.fft = fftCanvas;
    this.readout = readout;
    this.analyser = null;
  }

  attach(ctx, source) {
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 8192;
    this.analyser.smoothingTimeConstant = 0.5;
    source.connect(this.analyser);
    this.rate = ctx.sampleRate;
    this.time = new Float32Array(this.analyser.fftSize);
    this.freq = new Float32Array(this.analyser.frequencyBinCount);
  }

  static prepare(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth,
      h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr))
      canvas.width = Math.round(w * dpr);
    if (canvas.height !== Math.round(h * dpr))
      canvas.height = Math.round(h * dpr);
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = "#0b0f14";
    g.fillRect(0, 0, w, h);
    g.font = "11px system-ui, sans-serif";
    return { g, w, h };
  }

  /** `expectedHz` = fundamental the model predicts (0 when silent), used for the time base and markers. */
  draw(expectedHz) {
    if (!this.scope.clientWidth) return; // section collapsed or panel hidden
    if (!this.analyser) {
      for (const c of [this.scope, this.fft]) {
        const { g, h } = SoundViewer.prepare(c);
        g.fillStyle = "#8796a5";
        g.fillText("start audio to see the signal", 10, h / 2);
      }
      return;
    }
    this.analyser.getFloatTimeDomainData(this.time);
    this.analyser.getFloatFrequencyData(this.freq);
    const peakDb = this.drawScope(expectedHz);
    const peakHz = this.drawSpectrum(expectedHz);
    this.readout.textContent =
      peakDb > -90
        ? `level ${peakDb.toFixed(1)} dBFS · strongest ${peakHz.toFixed(1)} Hz${expectedHz ? ` · expected ${expectedHz.toFixed(1)} Hz` : ""}`
        : "silent";
  }

  drawScope(f) {
    const { g, w, h } = SoundViewer.prepare(this.scope);
    const x = this.time,
      n = x.length;
    let peak = 0;
    for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs(x[i]));
    // show ~3 periods, triggered on a rising zero crossing so the trace stands still
    const span = Math.min(
      Math.max(Math.round(f ? (3 * this.rate) / f : 0.01 * this.rate), 64),
      n >> 1,
    );
    let trig = 0;
    for (let i = 1; i < n - span; i++) {
      if (x[i - 1] < 0 && x[i] >= 0) {
        trig = i;
        break;
      }
    }
    const scale = (h / 2 - 6) / Math.max(peak, 0.02);
    g.strokeStyle = "#1e2833";
    g.beginPath();
    g.moveTo(0, h / 2);
    g.lineTo(w, h / 2);
    g.stroke();
    g.strokeStyle = "#4fc3f7";
    g.lineWidth = 1.5;
    g.beginPath();
    for (let i = 0; i < span; i++) {
      const px = (i / (span - 1)) * w,
        py = h / 2 - x[trig + i] * scale;
      if (i === 0) g.moveTo(px, py);
      else g.lineTo(px, py);
    }
    g.stroke();
    g.fillStyle = "#8796a5";
    g.fillText(
      `${((span / this.rate) * 1000).toFixed(2)} ms · auto-scaled`,
      6,
      13,
    );
    return peak > 0 ? 20 * Math.log10(peak) : -Infinity;
  }

  drawSpectrum(f) {
    const { g, w, h } = SoundViewer.prepare(this.fft);
    const binHz = this.rate / (2 * this.freq.length);
    const fx = (hz) => (Math.log10(hz / F_MIN) / Math.log10(F_MAX / F_MIN)) * w;
    const dy = (db) =>
      h -
      ((Math.min(Math.max(db, DB_MIN), DB_MAX) - DB_MIN) / (DB_MAX - DB_MIN)) *
        h;

    g.strokeStyle = "#1e2833";
    g.fillStyle = "#5b6b7a";
    for (const hz of [50, 100, 200, 500, 1000, 2000, 5000, 10000]) {
      g.beginPath();
      g.moveTo(fx(hz), 0);
      g.lineTo(fx(hz), h);
      g.stroke();
      g.fillText(hz >= 1000 ? `${hz / 1000}k` : `${hz}`, fx(hz) + 2, h - 3);
    }
    for (const db of [-30, -60, -90]) {
      g.beginPath();
      g.moveTo(0, dy(db));
      g.lineTo(w, dy(db));
      g.stroke();
      g.fillText(`${db}`, 2, dy(db) - 2);
    }
    if (f) {
      // a square wave only has odd harmonics: mark the 1st, 3rd, 5th, 7th
      g.strokeStyle = "rgba(255, 213, 79, 0.45)";
      g.setLineDash([3, 3]);
      for (const k of [1, 3, 5, 7]) {
        if (k * f > F_MAX) break;
        g.beginPath();
        g.moveTo(fx(k * f), 0);
        g.lineTo(fx(k * f), h);
        g.stroke();
      }
      g.setLineDash([]);
    }

    let best = -Infinity,
      bestHz = 0;
    g.fillStyle = "rgba(129, 199, 132, 0.35)";
    g.strokeStyle = "#81c784";
    g.beginPath();
    g.moveTo(0, h);
    for (let i = 1; i < this.freq.length; i++) {
      const hz = i * binHz;
      if (hz < F_MIN) continue;
      if (hz > F_MAX) break;
      const db = this.freq[i];
      if (db > best) {
        best = db;
        bestHz = hz;
      }
      g.lineTo(fx(hz), dy(db));
    }
    g.lineTo(w, h);
    g.closePath();
    g.fill();
    g.stroke();
    // refine the strongest bin with parabolic interpolation
    const i = Math.round(bestHz / binHz);
    if (i > 0 && i < this.freq.length - 1) {
      const a = this.freq[i - 1],
        b = this.freq[i],
        c = this.freq[i + 1];
      const d = a - 2 * b + c;
      if (d < 0) bestHz = (i + (0.5 * (a - c)) / d) * binHz;
    }
    return bestHz;
  }
}
