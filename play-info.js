// What each panel control does, with a live value computed from the same model the audio uses.
import {
  deriveParams,
  f555,
  lfoRate,
  octaveIndex,
  pitch,
} from "./synth-model.js";

// Computer keyboard -> keypad key 1..20 (piano layout: home row = naturals, row above = sharps)
export const KEY_CODES = [
  "KeyA",
  "KeyW",
  "KeyS",
  "KeyD",
  "KeyR",
  "KeyF",
  "KeyT",
  "KeyG",
  "KeyH",
  "KeyU",
  "KeyJ",
  "KeyI",
  "KeyK",
  "KeyO",
  "KeyL",
  "Semicolon",
  "BracketLeft",
  "Quote",
  "BracketRight",
  "Enter",
];
export const KEY_LABELS = [
  "A",
  "W",
  "S",
  "D",
  "R",
  "F",
  "T",
  "G",
  "H",
  "U",
  "J",
  "I",
  "K",
  "O",
  "L",
  ";",
  "[",
  "'",
  "]",
  "⏎",
];

const sign = (v, d = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}`;
const pct = (v) => `${Math.round(v * 100)} %`;

function centsVsMid(model, s, id, key) {
  return (
    1200 *
    Math.log2(
      pitch(model, s, key).f555 / pitch(model, { ...s, [id]: 0.5 }, key).f555,
    )
  );
}

export function vibratoCents(model, s) {
  const p = deriveParams(model, { ...s, vibrato: true }, 10);
  return (
    600 *
    Math.log2(
      f555(p.rc, p.vc0 - p.cvDev, p.vdd) / f555(p.rc, p.vc0 + p.cvDev, p.vdd),
    )
  );
}

function volumeDb(model, s) {
  return (
    20 *
    Math.log10(
      deriveParams(model, s, 1).kAmp /
        deriveParams(model, { ...s, volume: 1 }, 1).kAmp,
    )
  );
}

const INFO = {
  volume: {
    title: "VOLUME · RV1 10 kΩ log",
    role:
      "Divides the audio coming out of the tone network before the LM386 power amp (gain 20). " +
      "Log taper, so equal turns sound like equal loudness steps.",
    value: (m, s) => `${pct(s.volume)} → ${volumeDb(m, s).toFixed(1)} dB`,
    short: (m, s) => pct(s.volume),
  },
  depth: {
    title: "DEPTH · RV3 10 kΩ linear",
    role:
      "How far the vibrato bends the pitch. Taps the LFO wave and injects it into the 555 CV pin " +
      "through R14 4k7 / C20. The R14 load makes it non-linear: most of the range is in the last quarter.",
    value: (m, s) =>
      `±${vibratoCents(m, s).toFixed(1)} cents${s.vibrato ? "" : " (VIB is off)"}`,
    short: (m, s) => `±${vibratoCents(m, s).toFixed(0)} c`,
  },
  tune: {
    title: "TUNE · RV4 2 kΩ trimmer (calibration)",
    role:
      "Adds resistance in series with the whole key ladder, so it moves the top keys about 3× more " +
      "than the bottom keys. Calibrate on key 20, then SPAN on key 1, repeat 2–3×.",
    value: (m, s) =>
      `key 1 ${sign(centsVsMid(m, s, "tune", 1))} c · key 20 ${sign(centsVsMid(m, s, "tune", 20))} c (vs mid)`,
    short: (m, s) => `${sign(centsVsMid(m, s, "tune", 20), 0)} c @20`,
  },
  span: {
    title: "SPAN · RV5 1 kΩ trimmer (calibration)",
    role:
      "Sets the 555 control voltage (CV divider R4/R5). CV sets both switching thresholds, so every key " +
      "shifts by the same number of cents: it transposes the keyboard.",
    value: (m, s) =>
      `CV ${deriveParams(m, s, 1).vc0.toFixed(3)} V · all keys ${sign(centsVsMid(m, s, "span", 10))} c (vs mid)`,
    short: (m, s) => `${sign(centsVsMid(m, s, "span", 10), 0)} c`,
  },
  rate: {
    title: "RATE · RV2 100 kΩ trimmer",
    role:
      "Vibrato speed. It is the charging resistance (with R13 68 kΩ) of C18 1 µF in the LM358 " +
      "relaxation oscillator. Higher setting = more resistance = slower.",
    value: (m, s) => `${lfoRate(m, s.rate).toFixed(2)} Hz`,
    short: (m, s) => `${lfoRate(m, s.rate).toFixed(1)} Hz`,
  },
  power: {
    title: "POWER · SW1",
    role:
      "Connects the battery / DC jack (after the 1N5819 reverse-polarity diode) to the +9 V rail. " +
      "The LP2950 5 V regulator, LED and all the chips follow.",
    value: (m, s) => (s.power ? "on" : "off"),
    short: (m, s) => (s.power ? "ON" : "OFF"),
  },
  vibrato: {
    title: "VIB · SW5",
    role:
      "Lets the LFO reach the CV pin. Off grounds the DEPTH wiper; the LFO keeps running and C20 keeps " +
      "its charge, so switching never clicks or jumps in pitch.",
    value: (m, s) => (s.vibrato ? "on" : "off"),
    short: (m, s) => (s.vibrato ? "on" : "off"),
  },
  oct_down1: {
    title: "OCT −1 · SW2",
    role: "Picks the next CD4040 divider output: one octave down. Octaves are exact because the counter divides by 2.",
    value: (m, s) =>
      `${s.oct_down1 ? "on" : "off"} → ${m.octaves[octaveIndex(s)]} (÷${2 ** (octaveIndex(s) + 1)})`,
    short: (m, s) => (s.oct_down1 ? "on" : "off"),
  },
  oct_down2: {
    title: "OCT −2 · SW3",
    role: "Switches to the ÷8 / ÷16 outputs: two octaves down (three with OCT −1 as well).",
    value: (m, s) =>
      `${s.oct_down2 ? "on" : "off"} → ${m.octaves[octaveIndex(s)]} (÷${2 ** (octaveIndex(s) + 1)})`,
    short: (m, s) => (s.oct_down2 ? "on" : "off"),
  },
  tone_soft: {
    title: "TONE · SW4",
    role:
      "Soft grounds C10 47 nF after R7 150 kΩ: a gentle low-pass (about 630 Hz corner with the load) " +
      "that rounds off the buzzy square wave. Bright leaves the full harmonics.",
    value: (m, s) => (s.tone_soft ? "soft" : "bright"),
    short: (m, s) => (s.tone_soft ? "soft" : "bright"),
  },
  phones: {
    title: "PHONES · J4",
    role:
      "Plugging in breaks the speaker connection; headphones are fed through R9 220 Ω instead, " +
      "which is much quieter and keeps more bass.",
    value: (m, s) =>
      s.phones ? "plugged in (speaker muted)" : "empty (speaker on)",
    short: (m, s) => (s.phones ? "plugged" : ""),
  },
  key: {
    title: "KEYPAD · K1",
    role:
      "The stylus connects the 555 timing pin to one tap of the resistor ladder. Further left = more " +
      "resistance = slower charging = lower note. Keyboard: home row = white keys, row above = sharps.",
    value: (m, s, key) => {
      const p = key ? pitch(m, s, key) : null;
      return p
        ? `${p.note}: 555 ${p.f555.toFixed(1)} Hz → out ${p.fOut.toFixed(2)} Hz`
        : "stylus up";
    },
    short: () => "",
  },
};

export const LABEL_NAMES = {
  volume: "VOLUME",
  depth: "DEPTH",
  tune: "TUNE",
  span: "SPAN",
  rate: "RATE",
  power: "POWER",
  vibrato: "VIB",
  oct_down1: "OCT−1",
  oct_down2: "OCT−2",
  tone_soft: "TONE",
  phones: "PHONES",
};

export function controlInfo(model, s, id, key = 0) {
  const i = INFO[id];
  return i
    ? { title: i.title, role: i.role, value: i.value(model, s, key) }
    : null;
}

export function shortValue(model, s, id) {
  return INFO[id]?.short(model, s) ?? "";
}
