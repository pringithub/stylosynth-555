// Behavioural StyloSynth-555 model shared by the Play UI and the audio worklet (no DOM access).

export const LN2 = Math.log(2);

export function logTaper(x) {
  return (81 ** x - 1) / 80;
}

/** TLC555 frequency with thresholds at Vc (upper) and Vc/2 (lower), charging between 0 and VDD. */
export function f555(rc, vc, vdd) {
  const v = Math.min(Math.max(vc, 0.2), vdd - 0.05);
  return 1 / (rc * (Math.log((vdd - v / 2) / (vdd - v)) + LN2));
}

export function cvNominal(model, span) {
  const { r_top, r_bot_fixed, r_int } = model.cv;
  const gTop = 1 / r_top + 1 / r_int;
  const gBot = 1 / (r_bot_fixed + span * model.span_r) + 1 / (2 * r_int);
  return (model.vdd * gTop) / (gTop + gBot);
}

function timingR(model, k, tune) {
  return k.r_cum_nominal + (tune - 0.5) * model.tune_r + model.r_series;
}

/** Per-key factor that anchors the formula to the SPICE ladder result at TUNE/SPAN mid. */
function calibration(model, k) {
  const fNominal = f555(
    timingR(model, k, 0.5) * model.c_t,
    cvNominal(model, 0.5),
    model.vdd,
  );
  return k.f_spice / fNominal;
}

export function lfoLevels(model) {
  const { r_hyst, out_hi_drop, out_lo } = model.lfo;
  const hi = model.vdd - out_hi_drop;
  // three equal resistors: VDD, GND and the op-amp output all meet at the + input
  return {
    outHi: hi,
    outLo: out_lo,
    thHi: (model.vdd + hi) / 3,
    thLo: (model.vdd + out_lo) / 3,
    r_hyst,
  };
}

export function lfoRate(model, rate) {
  const { outHi, outLo, thHi, thLo } = lfoLevels(model);
  const rc = (model.lfo.r_fixed + rate * model.lfo.r_trim) * model.lfo.c;
  return (
    1 /
    (rc *
      (Math.log((outHi - thLo) / (outHi - thHi)) +
        Math.log((thHi - outLo) / (thLo - outLo))))
  );
}

function interp(table, x) {
  if (x <= table[0][0]) return table[0][1];
  for (let i = 1; i < table.length; i++) {
    if (x <= table[i][0]) {
      const [x0, y0] = table[i - 1],
        [x1, y1] = table[i];
      return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
    }
  }
  return table[table.length - 1][1];
}

/** Loaded wiper ratio of the DEPTH pot, normalised to 1 at full rotation. */
function depthGain(model, x) {
  const { pot, r_load } = model.depth;
  const top = Math.max((1 - x) * pot, 0.5),
    bot = Math.max(x * pot, 0.5);
  const botL = (bot * r_load) / (bot + r_load);
  const full =
    (pot * r_load) / (pot + r_load) / (0.5 + (pot * r_load) / (pot + r_load));
  return botL / (top + botL) / full;
}

export function octaveIndex(s) {
  return (s.oct_down1 ? 1 : 0) + (s.oct_down2 ? 2 : 0);
}

/** Everything the worklet needs for the current panel state. `key` = 0 means the stylus is lifted. */
export function deriveParams(model, s, key) {
  const k = model.keys.find((e) => e.key === key);
  const fLfo = lfoRate(model, s.rate);
  const cvDev = s.vibrato
    ? interp(model.lfo.cv_dev_table, fLfo) * depthGain(model, s.depth)
    : 0;
  const x = logTaper(s.volume);
  const a = model.audio;
  const rt = Math.max((1 - x) * a.pot, 0.5);
  const rb = Math.max(x * a.pot, 0.5);
  const rbIn = (rb * a.r_in) / (rb + a.r_in);
  return {
    power: Boolean(s.power),
    active: Boolean(k),
    rc: k ? timingR(model, k, s.tune) * model.c_t : 1,
    kcal: k ? calibration(model, k) : 1,
    vdd: model.vdd,
    vc0: cvNominal(model, s.span),
    cvDev,
    lfo: {
      ...lfoLevels(model),
      rc: (model.lfo.r_fixed + s.rate * model.lfo.r_trim) * model.lfo.c,
    },
    divide: 2 ** (octaveIndex(s) + 1),
    toneSoft: Boolean(s.tone_soft),
    rSrc: a.r_src,
    cTone: a.c_tone,
    cCouple: a.c_couple,
    rLoad: rt + rbIn,
    kAmp: rbIn / (rt + rbIn),
    gain: a.gain,
    v9: Math.max(s.supply_v - a.supply_drop, 0),
    phones: Boolean(s.phones),
    rcOut: s.phones ? (a.r_hp_series + a.r_hp) * a.c_out : a.r_spk * a.c_out,
    outScale: s.phones ? a.r_hp / (a.r_hp_series + a.r_hp) : 1,
  };
}

/** Static pitch readout (LFO centred) for the HUD and for checking against SPICE. */
export function pitch(model, s, key) {
  const k = model.keys.find((e) => e.key === key);
  if (!k) return null;
  const p = deriveParams(model, s, key);
  const f = p.kcal * f555(p.rc, p.vc0, p.vdd);
  const oct = model.octaves[octaveIndex(s)];
  return {
    f555: f,
    fOut: f / p.divide,
    note: k.notes[oct],
    target: k.freqs[oct],
    cents: 1200 * Math.log2(f / p.divide / k.freqs[oct]),
    lfoHz: lfoRate(model, s.rate),
  };
}
