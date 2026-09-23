#!/usr/bin/env python3
"""Compute the 555 key-ladder values: fixed 1% E96 resistors + two calibration trimmers.

Topology: TLC555 pin3 -> R101 + TUNE trimmer -> key 20 (E, highest) -> R102 -> key 19 -> ... -> key 1 (A).
The stylus connects the touched key to the timing node, so the timing resistance is
R0 (555 output + stylus resistor) + the cumulative ladder resistance up to that key.
A CD4040 divides the 555 output by 2/4/8/16 to select the octave (exact octaves).

Calibration (two-point):
  TUNE  - trimmer in series with segment 0: an offset common to all keys (set on key 20)
  SPAN  - trimmer in the CV divider: scales every key by the same ratio (set on key 1)
Segment values are picked greedily so the *cumulative* ladder resistance tracks the target,
so E96 rounding never accumulates. A Monte Carlo run with part tolerances checks the result.

Writes hardware/design/ladder.json and hardware/design/ladder.csv.
"""
import csv
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "design"

VDD = 5.0
C_T = 22e-9                 # polypropylene film, 2.5 %
R0_NOM = 200.0              # TLC555 output (~100 ohm) + stylus series resistor R6 (100 ohm)
CV_R_TOP = 1.5e3
CV_R_BOT_FIXED = 2.4e3
SPAN_TRIM = 1e3
TUNE_TRIM = 2e3
DIVIDERS = {"BASS": 16, "LOW": 8, "MID": 4, "HIGH": 2}
HIGH_LOWEST_NOTE = ("A", 4)  # key 1 at the HIGH position
N_KEYS = 20

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
E96 = [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30, 1.33, 1.37, 1.40, 1.43,
       1.47, 1.50, 1.54, 1.58, 1.62, 1.65, 1.69, 1.74, 1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10,
       2.15, 2.21, 2.26, 2.32, 2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09,
       3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12, 4.22, 4.32, 4.42, 4.53,
       4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49, 5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65,
       6.81, 6.98, 7.15, 7.32, 7.50, 7.68, 7.87, 8.06, 8.25, 8.45, 8.66, 8.87, 9.09, 9.31, 9.53, 9.76]
E96_ALL = sorted(round(v * 10 ** d, 6) for d in range(1, 6) for v in E96)


def midi(name, octave):
    return 12 * (octave + 1) + NOTE_NAMES.index(name)


def note_freq(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def note_label(m):
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def fmt_r(r):
    if r >= 1e6:
        s, unit = f"{r / 1e6:.3g}", "M"
    elif r >= 1e3:
        s, unit = f"{r / 1e3:.3g}", "k"
    else:
        return f"{r:.3g}"
    return s.replace(".", unit) if "." in s else s + unit


def vc(r_bot, r_int=None):
    """CV node voltage for the external divider (optionally loaded by the 555's internal divider)."""
    if r_int is None:
        return VDD * r_bot / (CV_R_TOP + r_bot)
    # internal divider: R_int from VDD to CV, 2*R_int from CV to GND
    g_top, g_bot = 1 / CV_R_TOP + 1 / r_int, 1 / r_bot + 1 / (2 * r_int)
    return VDD * g_top / (g_top + g_bot)


def period_factor(v_c):
    """T = R*C*factor for a rail-to-rail 555: charge Vc/2 -> Vc toward VDD, discharge Vc -> Vc/2."""
    return math.log((VDD - v_c / 2) / (VDD - v_c)) + math.log(2)


def freq(r_total, c, v_c):
    return 1.0 / (r_total * c * period_factor(v_c))


def nearest_e96(x):
    return min(E96_ALL, key=lambda v: abs(v - x))


def design():
    m_low = midi(*HIGH_LOWEST_NOTE)
    keys = list(range(m_low, m_low + N_KEYS))
    f555 = {m: note_freq(m) * DIVIDERS["HIGH"] for m in keys}
    vc_nom = vc(CV_R_BOT_FIXED + SPAN_TRIM / 2)
    r_target = {m: 1 / (f555[m] * C_T * period_factor(vc_nom)) - R0_NOM for m in keys}

    order = list(reversed(keys))                      # segment 0 feeds the highest key
    seg0_fixed = nearest_e96(r_target[order[0]] - TUNE_TRIM / 2)
    fixed = [seg0_fixed]
    cum = r_target[order[0]]                           # TUNE absorbs segment-0 rounding, so track the ideal
    for m in order[1:]:
        v = nearest_e96(r_target[m] - cum)
        fixed.append(v)
        cum += v
    return keys, order, f555, r_target, fixed, vc_nom


def ladder_freqs(fixed, tune, span, c, r0, tol=None, r_int=None):
    tol = tol or [0.0] * len(fixed)
    v_c = vc(CV_R_BOT_FIXED + span, r_int)
    cum, out = r0 + tune, []
    for v, e in zip(fixed, tol):
        cum += v * (1 + e)
        out.append(freq(cum, c, v_c))
    return out                                          # in ladder order (highest key first)


def calibrate(fixed, targets, c, r0, tol, r_int):
    """Emulate the two-point tuning procedure; returns (tune, span) or None if out of range."""
    tune, span = TUNE_TRIM / 2, SPAN_TRIM / 2
    for _ in range(12):
        lo, hi = 0.0, TUNE_TRIM                          # key 20 with TUNE
        for _ in range(50):
            mid = (lo + hi) / 2
            f = ladder_freqs(fixed, mid, span, c, r0, tol, r_int)[0]
            lo, hi = (mid, hi) if f > targets[0] else (lo, mid)
        tune = (lo + hi) / 2
        lo, hi = 0.0, SPAN_TRIM                          # key 1 with SPAN (more span -> higher Vc -> lower f)
        for _ in range(50):
            mid = (lo + hi) / 2
            f = ladder_freqs(fixed, tune, mid, c, r0, tol, r_int)[-1]
            lo, hi = (mid, hi) if f > targets[-1] else (lo, mid)
        span = (lo + hi) / 2
    fs = ladder_freqs(fixed, tune, span, c, r0, tol, r_int)
    if abs(1200 * math.log2(fs[0] / targets[0])) > 1 or abs(1200 * math.log2(fs[-1] / targets[-1])) > 1:
        return None
    return tune, span


def monte_carlo(fixed, targets, trials=2000, r_tol=0.01, c_tol=0.025, seed=1):
    rng = random.Random(seed)
    worst, failures = [], 0
    for _ in range(trials):
        c = C_T * (1 + rng.uniform(-c_tol, c_tol))
        r0 = rng.uniform(100, 700)
        r_int = rng.uniform(20e3, 300e3)
        tol = [rng.uniform(-r_tol, r_tol) for _ in fixed]
        cal = calibrate(fixed, targets, c, r0, tol, r_int)
        if cal is None:
            failures += 1
            continue
        fs = ladder_freqs(fixed, *cal, c, r0, tol, r_int)
        worst.append(max(abs(1200 * math.log2(f / t)) for f, t in zip(fs, targets)))
    worst.sort()
    pct = lambda p: round(worst[int(p * (len(worst) - 1))], 2) if worst else None
    return {"trials": trials, "r_tol": r_tol, "c_tol": c_tol, "calibration_failures": failures,
            "worst_key_cents_median": pct(0.5), "worst_key_cents_p95": pct(0.95), "worst_key_cents_max": pct(1.0)}


def main():
    keys, order, f555, r_target, fixed, vc_nom = design()
    targets = [f555[m] for m in order]
    nominal = ladder_freqs(fixed, TUNE_TRIM / 2, SPAN_TRIM / 2, C_T, R0_NOM)
    mc_1pct = monte_carlo(fixed, targets)
    mc_01pct = monte_carlo(fixed, targets, r_tol=0.001)

    segments, cum = [], R0_NOM + TUNE_TRIM / 2
    for i, (m, v) in enumerate(zip(order, fixed)):
        cum += v
        segments.append({
            "segment": i,
            "key": keys.index(m) + 1,
            "note_high": note_label(m),
            "f555_hz": round(f555[m], 3),
            "r_target_cum_ohm": round(r_target[m], 1),
            "r_fixed_ohm": v,
            "r_fixed": fmt_r(v),
            "r_cum_nominal_ohm": round(cum - R0_NOM, 1),
            "nominal_error_cents": round(1200 * math.log2(nominal[i] / f555[m]), 2),
            "notes": {pos: note_label(m - 12 * (int(math.log2(d)) - 1)) for pos, d in DIVIDERS.items()},
            "freqs_hz": {pos: round(f555[m] / d, 2) for pos, d in DIVIDERS.items()},
        })

    result = {
        "c_t_farad": C_T, "vdd": VDD, "r0_nominal_ohm": R0_NOM,
        "cv_r_top_ohm": CV_R_TOP, "cv_r_bot_fixed_ohm": CV_R_BOT_FIXED, "vc_nominal_v": round(vc_nom, 4),
        "tune_trimmer_ohm": TUNE_TRIM, "span_trimmer_ohm": SPAN_TRIM,
        "dividers": DIVIDERS,
        "f555_range_hz": [round(min(f555.values()), 2), round(max(f555.values()), 2)],
        "monte_carlo_1pct": mc_1pct, "monte_carlo_0p1pct": mc_01pct,
        "segments": segments,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ladder.json").write_text(json.dumps(result, indent=2))
    with open(OUT_DIR / "ladder.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["segment", "key", *DIVIDERS, "f555_Hz", "R_fixed", "R_cum_nominal", "nominal_err_cents"])
        for s in segments:
            w.writerow([s["segment"], s["key"], *(s["notes"][p] for p in DIVIDERS), s["f555_hz"],
                        s["r_fixed"], s["r_cum_nominal_ohm"], s["nominal_error_cents"]])

    print(f"C_T {C_T * 1e9:g} nF, Vc nominal {vc_nom:.3f} V, 555 range {result['f555_range_hz']} Hz")
    print(f"{'seg':>3} {'key':>3} {'notes (B/L/M/H)':<18} {'R':>6} {'err ct':>7}")
    for s in segments:
        n = "/".join(s["notes"][p] for p in DIVIDERS)
        print(f"{s['segment']:>3} {s['key']:>3} {n:<18} {s['r_fixed']:>6} {s['nominal_error_cents']:>7.2f}")
    print("Monte Carlo 1% resistors  :", mc_1pct)
    print("Monte Carlo 0.1% resistors:", mc_01pct)


if __name__ == "__main__":
    main()
