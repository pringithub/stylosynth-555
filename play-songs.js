// Scripted songs for Play mode, and a small sequencer that drives the stylus.
// Melodies are public domain (traditional or pre-1900) except "Space Echo", written for this project.
//
// A song is a list of sections; each section may change the panel settings and pedals and is played in
// whichever octave-switch range fits its notes. Notation inside `notes` (whitespace separated):
//   F#4/1        note F#4 for 1 beat           -/2          rest for 2 beats
//   A3>F#4/1     stylus glide from A3 up to F#4, landing early and holding for the rest of the beat
//   G4~A4/2      trill between G4 and A4         {depth=0.8,delay.mix=0.5,tone=soft}  automation
//   |            bar line (ignored)
import { PEDAL_DEFAULTS } from "./play-fx.js";

export const SONGS = [
  {
    id: "ode",
    title: "Ode to Joy",
    credit: "L. v. Beethoven, 1824",
    bpm: 108,
    beatsPerBar: 4,
    pedals: {
      reverb: { on: true, decay: 3, tone: 0.5, mix: 0.4 },
      phaser: { on: true, rate: 0.15, depth: 0.9, res: 0.5, mix: 0.7 },
    },
    sections: [
      {
        name: "intro (low, phased)",
        transpose: -12,
        settings: { tone_soft: true, vibrato: false, volume: 0.65 },
        notes: `F#4/1 F#4/1 G4/1 A4/1 | A4/1 G4/1 F#4/1 E4/1 | D4/1 D4/1 E4/1 F#4/1 | F#4/1.5 E4/0.5 E4/2`,
      },
      {
        name: "theme",
        settings: {
          tone_soft: true,
          vibrato: true,
          depth: 0.35,
          rate: 0.55,
          volume: 0.6,
        },
        pedals: {
          phaser: { on: false },
          delay: {
            on: true,
            beats: 0.75,
            feedback: 0.3,
            tone: 0.45,
            width: 0.8,
            mix: 0.25,
          },
          reverb: { decay: 2.6, mix: 0.35 },
        },
        notes: `F#4/1 F#4/1 G4/1 A4/1 | A4/1 G4/1 F#4/1 E4/1 | D4/1 D4/1 E4/1 F#4/1 | E4/1.5 D4/0.5 D4/2 |
                {depth=0.55,phaser.on=true} E4/1 E4/1 F#4/1 D4/1 | E4/1 F#4/0.5 G4/0.5 F#4/1 D4/1 |
                E4/1 F#4/0.5 G4/0.5 F#4/1 E4/1 | D4/1 E4/1 {depth=0.8} A3/2 |
                {depth=0.35,phaser.on=false} F#4/1 F#4/1 G4/1 A4/1 | A4/1 G4/1 F#4/1 E4/1 |
                D4/1 D4/1 E4/1 F#4/1 | E4/1.5 D4/0.5 D4/2`,
      },
      {
        name: "finale (high, ping-pong echo)",
        transpose: 12,
        settings: { tone_soft: false, vibrato: true, depth: 0.4, volume: 0.55 },
        pedals: {
          delay: { feedback: 0.45, width: 1, mix: 0.45 },
          reverb: { decay: 4, mix: 0.4 },
        },
        notes: `A3>F#4/1 F#4/1 G4/1 A4/1 | A4/1 G4/1 F#4/1 E4/1 | D4/1 D4/1 E4/1 F#4/1 | F#4/1.5 E4/0.5 E4/2 |
                F#4/1 F#4/1 G4/1 A4/1 | A4/1 G4/1 F#4/1 E4/1 | D4/1 D4/1 E4/1 F#4/1 | E4/1.5 D4/0.5 {depth=0.8} D4/2 |
                {tone=soft,depth=0.4} D4/0.5 F#4/0.5 A4/0.5 {depth=0.75} D5/2.5 | -/4`,
      },
    ],
  },
  {
    id: "twinkle",
    title: "Twinkle, Twinkle, Little Star",
    credit: "traditional",
    bpm: 100,
    beatsPerBar: 4,
    pedals: { reverb: { on: true, decay: 3.5, mix: 0.4 } },
    sections: [
      {
        name: "music box",
        settings: {
          tone_soft: true,
          vibrato: true,
          depth: 0.25,
          rate: 0.45,
          volume: 0.6,
        },
        notes: `C4/1 C4/1 G4/1 G4/1 | A4/1 A4/1 G4/2 | F4/1 F4/1 E4/1 E4/1 | D4/1 D4/1 C4/2 |
                G4/1 G4/1 F4/1 F4/1 | E4/1 E4/1 D4/2 | G4/1 G4/1 F4/1 F4/1 | E4/1 E4/1 D4/2`,
      },
      {
        name: "sparkle (high, echoes)",
        transpose: 12,
        settings: { tone_soft: false, depth: 0.35 },
        pedals: {
          delay: {
            on: true,
            beats: 0.75,
            feedback: 0.4,
            tone: 0.55,
            width: 1,
            mix: 0.4,
          },
          reverb: { decay: 4.5 },
        },
        notes: `C4/1 C4/1 C4>G4/1 G4/1 | A4/1 A4/1 G4~A4/2 | F4/1 F4/1 E4/1 E4/1 | D4/1 D4/1 C4/2 |
                G4/1 G4/1 F4/1 F4/1 | E4/1 E4/1 D4~E4/2 | G4/1 G4/1 F4/1 F4/1 | E4/1 E4/1 D4/2 |
                C4/1 C4/1 C4>G4/1 G4/1 | A4/1 A4/1 G4/2 | F4/1 F4/1 E4/1 E4/1 | D4/1 D4/1 {depth=0.7,tone=soft} C4/6 | -/4`,
      },
    ],
  },
  {
    id: "greensleeves",
    title: "Greensleeves",
    credit: "traditional English",
    bpm: 96,
    beatsPerBar: 3,
    pedals: {
      phaser: { on: true, rate: 0.18, depth: 0.7, res: 0.3, mix: 0.6 },
      reverb: { on: true, decay: 3.5, mix: 0.4 },
    },
    sections: [
      {
        name: "verse (low, soft)",
        transpose: -17,
        settings: { tone_soft: true, vibrato: false, volume: 0.65 },
        notes: `A4/1 | C5/2 D5/1 | E5/1.5 F5/0.5 E5/1 | D5/2 B4/1 | G4/1.5 A4/0.5 B4/1 | C5/2 A4/1 |
                A4/1.5 G#4/0.5 A4/1 | B4/2 G#4/1 | E4/2 A4/1 | C5/2 D5/1 | E5/1.5 F5/0.5 E5/1 | D5/2 B4/1 |
                G4/1.5 A4/0.5 B4/1 | C5/1.5 B4/0.5 A4/1 | G#4/1.5 F#4/0.5 G#4/1 | A4/3 | -/2`,
      },
      {
        name: "verse (mid, vibrato + echo)",
        transpose: -5,
        settings: { vibrato: true, depth: 0.45, rate: 0.4, volume: 0.6 },
        pedals: {
          phaser: { mix: 0.4 },
          delay: {
            on: true,
            beats: 1.5,
            feedback: 0.35,
            tone: 0.4,
            width: 0.9,
            mix: 0.3,
          },
        },
        notes: `A4/1 | C5/2 D5/1 | E5/1.5 F5/0.5 E5/1 | {depth=0.7} D5/2 {depth=0.45} B4/1 | G4/1.5 A4/0.5 B4/1 |
                C5/2 A4/1 | A4/1.5 G#4/0.5 A4/1 | {depth=0.7} B4/2 {depth=0.45} G#4/1 | E4/2 A4/1 | C5/2 D5/1 |
                E5/1.5 F5/0.5 E5/1 | D5/2 B4/1 | G4/1.5 A4/0.5 B4/1 | C5/1.5 B4/0.5 A4/1 | G#4~A4/1.5 F#4/0.5 G#4/1 |
                {depth=0.75} A4/3 | -/2`,
      },
    ],
  },
  {
    id: "korobeiniki",
    title: "Korobeiniki",
    credit: "Russian folk song, 1861",
    bpm: 144,
    beatsPerBar: 4,
    pedals: {
      phaser: { on: true, rate: 1.2, depth: 0.6, res: 0.5, mix: 0.6 },
      delay: {
        on: true,
        beats: 0.5,
        feedback: 0.25,
        tone: 0.4,
        width: 1,
        mix: 0.25,
      },
      reverb: { on: true, decay: 1.6, mix: 0.2 },
    },
    sections: [
      {
        name: "high, bright",
        settings: { tone_soft: false, vibrato: false, volume: 0.55 },
        notes: `E5/1 B4/0.5 C5/0.5 D5/1 C5/0.5 B4/0.5 | A4/1 A4/0.5 C5/0.5 E5/1 D5/0.5 C5/0.5 |
                B4/1.5 C5/0.5 D5/1 E5/1 | C5/1 A4/1 A4/2 |
                D5/1.5 F5/0.5 A5/1 G5/0.5 F5/0.5 | E5/1.5 C5/0.5 E5/1 D5/0.5 C5/0.5 |
                B4/1 B4/0.5 C5/0.5 D5/1 E5/1 | C5/1 A4/1 A4/1 -/1`,
      },
      {
        name: "an octave down, soft with vibrato",
        transpose: -12,
        settings: { tone_soft: true, vibrato: true, depth: 0.3, rate: 0.2 },
        pedals: {
          phaser: { on: false },
          delay: { beats: 0.75, feedback: 0.35, mix: 0.35 },
        },
        notes: `E5/1 B4/0.5 C5/0.5 D5/1 C5/0.5 B4/0.5 | A4/1 A4/0.5 C5/0.5 E5/1 D5/0.5 C5/0.5 |
                B4/1.5 C5/0.5 D5/1 E5/1 | C5/1 A4/1 A4/2 |
                D5/1.5 F5/0.5 A5/1 G5/0.5 F5/0.5 | E5/1.5 C5/0.5 E5/1 D5/0.5 C5/0.5 |
                B4/1 B4/0.5 C5/0.5 D5/1 E5/1 | C5/1 A4/1 A4/1 -/1`,
      },
      {
        name: "back up, full pedals",
        settings: { tone_soft: false, depth: 0.2 },
        pedals: { phaser: { on: true }, delay: { beats: 0.5, mix: 0.3 } },
        notes: `E5/1 B4/0.5 C5/0.5 D5/1 C5/0.5 B4/0.5 | A4/1 A4/0.5 C5/0.5 E5/1 D5/0.5 C5/0.5 |
                B4/1.5 C5/0.5 D5/1 E5/1 | C5/1 A4/1 A4/2 |
                D5/1.5 F5/0.5 A5/1 G5/0.5 F5/0.5 | E5/1.5 C5/0.5 E5/1 D5/0.5 C5/0.5 |
                B4/1 B4/0.5 C5/0.5 D5/1 E5/1 | C5/1 A4/1 A4>E5/2 | -/4`,
      },
    ],
  },
  {
    id: "frere",
    title: "Frère Jacques (as a round)",
    credit: "traditional French",
    bpm: 108,
    beatsPerBar: 4,
    // a 2-bar echo with high feedback turns the single melody into a canon
    pedals: {
      delay: {
        on: true,
        beats: 8,
        feedback: 0.7,
        tone: 1,
        width: 0.8,
        mix: 0.75,
      },
      reverb: { on: true, decay: 1.8, mix: 0.25 },
    },
    sections: [
      {
        name: "round",
        transpose: 2,
        settings: { tone_soft: true, vibrato: false, volume: 0.55 },
        notes: `C4/1 D4/1 E4/1 C4/1 | C4/1 D4/1 E4/1 C4/1 | E4/1 F4/1 G4/2 | E4/1 F4/1 G4/2 |
                G4/0.5 A4/0.5 G4/0.5 F4/0.5 E4/1 C4/1 | G4/0.5 A4/0.5 G4/0.5 F4/0.5 E4/1 C4/1 |
                C4/1 G3/1 C4/2 | C4/1 G3/1 C4/2 | -/16`,
      },
    ],
  },
  {
    id: "daisy",
    title: "Daisy Bell (first lines)",
    credit: "Harry Dacre, 1892",
    bpm: 150,
    beatsPerBar: 3,
    pedals: {
      reverb: { on: true, decay: 2.8, mix: 0.4 },
      delay: {
        on: true,
        beats: 1.5,
        feedback: 0.3,
        tone: 0.35,
        width: 0.8,
        mix: 0.2,
      },
    },
    sections: [
      {
        name: "verse",
        transpose: -7,
        settings: {
          tone_soft: true,
          vibrato: true,
          depth: 0.4,
          rate: 0.5,
          volume: 0.6,
        },
        notes: `G5/3 | E5/3 | C5/3 | G4/3 | A4/1 B4/1 C5/1 | A4/2 C5/1 | {depth=0.7} G4/6 |
                {depth=0.4} D5/3 | G5/3 | E5/3 | C5/3 | A4/1 B4/1 C5/1 | D5/2 E5/1 | {depth=0.7} D5/6`,
      },
      {
        name: "reprise, winding down",
        transpose: -7,
        settings: { depth: 0.55 },
        pedals: {
          phaser: { on: true, rate: 0.1, depth: 0.8, res: 0.4, mix: 0.6 },
          reverb: { decay: 5, mix: 0.5 },
        },
        notes: `E5>G5/3 | G5>E5/3 | E5>C5/3 | C5>G4/3 | A4/1 B4/1 C5/1 | A4/2 C5/1 | G4/6 |
                {depth=0.8,rate=0.9} D5/3 | G5/3 | E5/3 | C5/3 | A4/1 B4/1 C5/1 | D5/2 E5/1 | {depth=1,rate=1} D5>G4/9 | -/3`,
      },
    ],
  },
  {
    id: "space",
    title: "Space Echo (arpeggio study)",
    credit: "original for this project",
    bpm: 116,
    beatsPerBar: 4,
    gate: 0.6,
    pedals: {
      phaser: { on: true, rate: 0.12, depth: 0.9, res: 0.6, mix: 0.7 },
      delay: {
        on: true,
        beats: 0.75,
        feedback: 0.45,
        tone: 0.45,
        width: 1,
        mix: 0.4,
      },
      reverb: { on: true, decay: 3.5, mix: 0.3 },
    },
    sections: [
      {
        name: "arpeggios",
        repeat: 3,
        settings: {
          tone_soft: false,
          vibrato: true,
          depth: 0.25,
          rate: 0.3,
          volume: 0.55,
        },
        notes: `A3/0.5 C4/0.5 E4/0.5 A4/0.5 C5/0.5 A4/0.5 E4/0.5 C4/0.5 |
                A3/0.5 C4/0.5 F4/0.5 A4/0.5 C5/0.5 A4/0.5 F4/0.5 C4/0.5 |
                C4/0.5 E4/0.5 G4/0.5 C5/0.5 E5/0.5 C5/0.5 G4/0.5 E4/0.5 |
                B3/0.5 D4/0.5 G4/0.5 B4/0.5 D5/0.5 B4/0.5 G4/0.5 D4/0.5`,
      },
      {
        name: "outro",
        settings: { tone_soft: true, depth: 0.6 },
        notes: "E5>A3/4 | -/4",
      },
    ],
  },
];

const KEYS_ON_PAD = 20;
const RANGE_ORDER = ["MID", "HIGH", "LOW", "BASS"];
const GLIDE_STEP_S = 0.045; // time per key while sliding the stylus
const TRILL_BEATS = 0.125;
const SETTING_KEYS = new Set([
  "depth",
  "rate",
  "volume",
  "vibrato",
  "tone",
  "tune",
  "span",
]);

export function noteToMidi(name) {
  const m = /^([A-G])([#b]?)(-?\d)$/.exec(name);
  if (!m) throw new Error(`bad note ${name}`);
  const base = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[m[1]];
  return (
    12 * (Number(m[3]) + 1) + base + (m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0)
  );
}

function parseValue(v) {
  if (v === "true" || v === "false") return v === "true";
  const n = Number(v);
  return Number.isFinite(n) ? n : v;
}

function parseDirective(tok) {
  const out = {};
  for (const part of tok.slice(1, -1).split(",")) {
    const [k, v] = part.split("=").map((x) => x.trim());
    const [pedal, param] = k.split(".");
    const known = param
      ? PEDAL_DEFAULTS[pedal] && param in PEDAL_DEFAULTS[pedal]
      : SETTING_KEYS.has(k);
    if (!known || v === undefined) throw new Error(`bad automation ${tok}`);
    out[k] = parseValue(v);
  }
  return out;
}

function parseNotes(text, transpose) {
  return (text.match(/\{[^}]*\}|[^\s|]+/g) || []).map((tok) => {
    if (tok.startsWith("{"))
      return { kind: "set", changes: parseDirective(tok) };
    const [pitches, beats] = tok.split("/");
    const b = Number(beats);
    if (!(b > 0)) throw new Error(`bad duration in ${tok}`);
    if (pitches === "-") return { kind: "rest", beats: b };
    const sep = pitches.includes(">")
      ? ">"
      : pitches.includes("~")
        ? "~"
        : null;
    const midis = (sep ? pitches.split(sep) : [pitches]).map(
      (n) => noteToMidi(n) + transpose,
    );
    return {
      kind: sep === ">" ? "glide" : sep === "~" ? "trill" : "note",
      midis,
      beats: b,
    };
  });
}

function pedalPreset(p, bpm) {
  const out = {};
  for (const [id, preset] of Object.entries(p || {})) {
    const { beats, ...rest } = preset;
    out[id] = beats ? { ...rest, time: (beats * 60) / bpm } : rest; // tempo-synced delay
  }
  return out;
}

/** Turn a song into timed events: key presses (with release times) and setting/pedal changes. */
export function compile(song, model) {
  const spb = 60 / song.bpm;
  const gate = song.gate ?? 0.85;
  const events = [];
  let t = 0;
  for (const sec of song.sections) {
    const steps = [];
    const body = parseNotes(
      sec.notes,
      (song.transpose || 0) + (sec.transpose || 0),
    );
    for (let r = 0; r < (sec.repeat || 1); r++) steps.push(...body);
    const pitched = steps.flatMap((s) => s.midis || []);
    const lo = Math.min(...pitched),
      hi = Math.max(...pitched);
    const range = RANGE_ORDER.find((name) => {
      const base = noteToMidi(model.keys[0].notes[name]);
      return lo >= base && hi < base + KEYS_ON_PAD;
    });
    if (!range)
      throw new Error(
        `${song.title} / ${sec.name}: notes don't fit any keypad range`,
      );
    const base = noteToMidi(model.keys[0].notes[range]);
    const oct = model.octaves.indexOf(range);
    events.push({
      t,
      kind: "set",
      section: sec.name,
      pedals: pedalPreset(sec.pedals, song.bpm),
      changes: {
        ...sec.settings,
        oct_down1: Boolean(oct & 1),
        oct_down2: Boolean(oct & 2),
      },
    });
    for (const s of steps) {
      if (s.kind === "set") {
        events.push({ t, kind: "set", changes: s.changes });
        continue;
      }
      if (s.kind === "rest") {
        t += s.beats;
        continue;
      }
      const keys = s.midis.map((m) => m - base + 1);
      const off = t + s.beats * gate;
      if (s.kind === "note") {
        events.push({ t, kind: "note", key: keys[0], off });
      } else if (s.kind === "glide") {
        const [a, b] = keys,
          n = Math.abs(b - a),
          dir = Math.sign(b - a);
        const step = Math.min(
          GLIDE_STEP_S / spb,
          (0.5 * s.beats) / Math.max(n, 1),
        );
        for (let i = 0; i < n; i++)
          events.push({
            t: t + i * step,
            kind: "note",
            key: a + dir * i,
            off: null,
          });
        events.push({ t: t + n * step, kind: "note", key: b, off });
      } else {
        for (let i = 0, tt = t; tt < off - 1e-9; i++, tt += TRILL_BEATS) {
          events.push({
            t: tt,
            kind: "note",
            key: keys[i % 2],
            off: tt + TRILL_BEATS >= off - 1e-9 ? off : null,
          });
        }
      }
      t += s.beats;
    }
  }
  return {
    song,
    events,
    totalBeats: t,
    pedals: pedalPreset(song.pedals, song.bpm),
    spb,
  };
}

export class SongPlayer {
  constructor(hooks) {
    this.hooks = hooks; // { press(key), release(), set(changes, pedals), progress(text), ended() }
    this.timer = null;
  }

  get playing() {
    return this.timer !== null;
  }

  play(compiled, loop) {
    this.stop();
    this.c = compiled;
    this.loop = loop;
    this.t0 = performance.now() / 1000 + 0.15;
    this.i = 0;
    this.off = null;
    this.section = "";
    this.timer = setInterval(() => this.tick(), 4);
  }

  stop() {
    if (this.timer === null) return;
    clearInterval(this.timer);
    this.timer = null;
    this.hooks.release();
  }

  tick() {
    const { events, totalBeats, song, spb } = this.c;
    const now = performance.now() / 1000 - this.t0;
    if (this.off !== null && now >= this.off * spb) {
      this.off = null;
      this.hooks.release();
    }
    while (this.i < events.length && now >= events[this.i].t * spb) {
      const e = events[this.i++];
      if (e.kind === "set") {
        if (e.section) this.section = e.section;
        this.hooks.set(e.changes, e.pedals || {});
        continue;
      }
      this.hooks.press(e.key);
      this.off = e.off;
    }
    const beat = Math.max(now / spb, 0);
    this.hooks.progress(
      `${this.section} · bar ${Math.floor(beat / song.beatsPerBar) + 1} / ${Math.ceil(totalBeats / song.beatsPerBar)}`,
    );
    if (
      this.i >= events.length &&
      this.off === null &&
      now >= totalBeats * spb
    ) {
      if (this.loop) {
        this.t0 += totalBeats * spb;
        this.i = 0;
      } else {
        this.stop();
        this.hooks.ended();
      }
    }
  }
}
