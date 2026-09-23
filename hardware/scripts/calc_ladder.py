#!/usr/bin/env python3
"""Compute the 555 key-ladder values (fixed resistor + trimmer per segment).

Topology: TLC555 pin3 -> seg0 -> key E (highest) -> seg1 -> key D# -> ... -> key A (lowest).
The stylus connects the touched key to the timing node (pins 2/6), so the timing
resistance is the cumulative ladder resistance up to that key.
A CD4040 divides the 555 output by 2/4/8/16 to select the octave.

Writes hardware/design/ladder.json and hardware/design/ladder.csv.
"""
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "design"

C_T = 22e-9                 # timing capacitor (polypropylene film)
K_555 = 1 / (2 * math.log(2))  # f = K / (R*C) for a rail-to-rail 555 in the 50%-duty topology
DIVIDERS = {"BASS": 16, "LOW": 8, "MID": 4, "HIGH": 2}
HIGH_LOWEST_NOTE = ("A", 4)  # key 1 at the HIGH position
N_KEYS = 20
TOL = 0.12                  # each segment must reach +/-12% of nominal (C_T 5%, R 1%, 555 3%, margin)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
       3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]
TRIMMERS = [100, 200, 500, 1e3, 2e3, 5e3, 10e3, 20e3, 50e3, 100e3]


def midi(name, octave):
    return 12 * (octave + 1) + NOTE_NAMES.index(name)


def note_freq(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def note_label(m):
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def e24_values():
    return sorted(v * 10 ** d for d in range(0, 7) for v in E24)


def e24_at_most(x):
    return max(v for v in e24_values() if v <= x + 1e-9)


def fmt_r(r):
    if r >= 1e6:
        return f"{r / 1e6:g}M"
    if r >= 1e3:
        return f"{r / 1e3:g}k"
    return f"{r:g}"


def design_segment(nominal, trimmer=None):
    lower, upper = nominal * (1 - TOL), nominal * (1 + TOL)
    if trimmer is None:
        trimmer = next(t for t in TRIMMERS if t >= 1.5 * (upper - lower))
    fixed = e24_at_most(min(lower, nominal - trimmer / 2))
    if fixed + trimmer < upper:
        raise ValueError(f"segment {nominal:.0f} ohm not coverable with {trimmer} trimmer")
    return fixed, trimmer, (nominal - fixed) / trimmer


def main():
    m_low = midi(*HIGH_LOWEST_NOTE)
    keys = list(range(m_low, m_low + N_KEYS))          # key 1 (left) .. key 20 (right), ascending
    f555 = {m: note_freq(m) * DIVIDERS["HIGH"] for m in keys}
    r_cum = {m: K_555 / (f555[m] * C_T) for m in keys}

    ladder_order = list(reversed(keys))                 # seg0 feeds the highest key
    segments = []
    prev = 0.0
    for i, m in enumerate(ladder_order):
        nominal = r_cum[m] - prev
        prev = r_cum[m]
        trimmer = None if i == 0 else 1e3               # one shared value for segs 1..19 keeps the BOM short
        fixed, trim, wiper = design_segment(nominal, trimmer)
        key_no = keys.index(m) + 1
        segments.append({
            "segment": i,
            "key": key_no,
            "note_high": note_label(m),
            "f555_hz": round(f555[m], 2),
            "r_cum_ohm": round(r_cum[m], 1),
            "r_nominal_ohm": round(nominal, 1),
            "r_fixed_ohm": fixed,
            "r_fixed": fmt_r(fixed),
            "trimmer_ohm": trim,
            "trimmer": fmt_r(trim),
            "wiper_at_nominal": round(wiper, 3),
            "notes": {pos: note_label(m - 12 * (int(math.log2(d)) - 1)) for pos, d in DIVIDERS.items()},
            "freqs_hz": {pos: round(f555[m] / d, 2) for pos, d in DIVIDERS.items()},
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "c_t_farad": C_T,
        "k_555": K_555,
        "tolerance_window": TOL,
        "dividers": DIVIDERS,
        "f555_range_hz": [round(min(f555.values()), 2), round(max(f555.values()), 2)],
        "segments": segments,
    }
    (OUT_DIR / "ladder.json").write_text(json.dumps(result, indent=2))
    with open(OUT_DIR / "ladder.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["segment", "key", "BASS", "LOW", "MID", "HIGH", "f555_Hz", "R_cum",
                    "R_nominal", "R_fixed", "trimmer", "wiper@nominal"])
        for s in segments:
            w.writerow([s["segment"], s["key"], *(s["notes"][p] for p in DIVIDERS),
                        s["f555_hz"], s["r_cum_ohm"], s["r_nominal_ohm"], s["r_fixed"],
                        s["trimmer"], s["wiper_at_nominal"]])

    print(f"C_T = {C_T * 1e9:g} nF, 555 range {result['f555_range_hz']} Hz")
    print(f"{'seg':>3} {'key':>3} {'notes (B/L/M/H)':<18} {'nominal':>9} {'fixed':>6} {'trim':>5} {'wiper':>6}")
    for s in segments:
        n = "/".join(s["notes"][p] for p in DIVIDERS)
        print(f"{s['segment']:>3} {s['key']:>3} {n:<18} {s['r_nominal_ohm']:>9.1f} "
              f"{s['r_fixed']:>6} {s['trimmer']:>5} {s['wiper_at_nominal']:>6.2f}")


if __name__ == "__main__":
    main()
