#!/usr/bin/env python3
"""Phase-1 simulations (ngspice via ctypes). Run with the project venv:
    .venv/bin/python hardware/sim/run_sims.py
Writes hardware/sim/results.json and prints a pass/fail summary.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import calc_ladder  # noqa: E402
from ngspice import NgSpice, rising_edges  # noqa: E402

HW = Path(__file__).resolve().parents[1]
LADDER = json.loads((HW / "design" / "ladder.json").read_text())
C_T = LADDER["c_t_farad"]
VDD = 5.0

# CV network: external divider (SPAN trimmer at mid-travel) swamps the unknown internal divider
CV_R_TOP = LADDER["cv_r_top_ohm"]
CV_R_BOT = LADDER["cv_r_bot_fixed_ohm"] + LADDER["span_trimmer_ohm"] / 2
CV_R_TH = CV_R_TOP * CV_R_BOT / (CV_R_TOP + CV_R_BOT)
R_INT_555 = 100e3            # assumed internal divider resistor (TLC555), swamped by the external one
R_STYLUS = 100.0             # R6
R_OUT_555 = 100.0            # modelled TLC555 output resistance

# Vibrato injection
R_SERIES_VIB = 4.7e3

# LFO (LM358 A relaxation oscillator + LM358 B follower)
LFO_C = 1e-6
LFO_R_FIXED = 68e3
LFO_R_TRIM = 100e3
LFO_R_HYST = 100e3

# Audio: 4040 output -> series R -> tone cap -> coupling cap -> volume pot -> LM386
R_AUDIO_SERIES = 150e3
C_TONE_SOFT = "47n"

def tlc555_ladder(r_timing, c_t=C_T, vcv_force=None):
    """Behavioural CMOS 555: thresholds at Vcv and Vcv/2 (Schmitt switch on normalised timing voltage)."""
    cv = (f"Vcvf cv 0 DC {vcv_force}" if vcv_force is not None else
          f"""Ri1 vdd cv {R_INT_555}
Ri2 cv lo {R_INT_555}
Ri3 lo 0 {R_INT_555}
Re1 vdd cv {CV_R_TOP}
Re2 cv 0 {CV_R_BOT}
Ccv cv 0 10n""")
    return f"""* TLC555 ladder oscillator
VDD vdd 0 DC {VDD}
{cv}
Bctl ctl 0 V = v(th)*{2 * VDD / 3}/max(v(cv),0.1)
S1 s 0 ctl 0 swm
V1 one 0 DC 1
Rs1 one s 1k
Bo outi 0 V = {VDD}*v(s)
Rout outi out {R_OUT_555}
Rlad out th {r_timing}
Ct th 0 {c_t} IC=0
Rpd th 0 10Meg
.model swm sw vt={VDD / 2} vh={VDD / 6} ron=1 roff=1e9
.tran 0.1u 16m 4m 0.1u uic
"""


def measure_freq(ng, netlist):
    ng.run(netlist)
    t, v = ng.vec("time"), ng.vec("out")
    edges = rising_edges(t, v, VDD / 2)
    if len(edges) < 4:
        raise RuntimeError("oscillator did not start")
    return 1.0 / np.mean(np.diff(edges[1:]))


def sim_ladder(ng):
    """Nominal ladder (TUNE/SPAN at mid) in ngspice vs. the analytic model used for the Monte Carlo."""
    segs = LADDER["segments"]
    model = calc_ladder.ladder_freqs([s["r_fixed_ohm"] for s in segs], LADDER["tune_trimmer_ohm"] / 2,
                                     LADDER["span_trimmer_ohm"] / 2, C_T, R_OUT_555 + R_STYLUS,
                                     r_int=R_INT_555)
    rows = []
    for seg, f_model in zip(segs, model):
        r = seg["r_cum_nominal_ohm"] + R_STYLUS
        f_sim = measure_freq(ng, tlc555_ladder(r))
        rows.append({"key": seg["key"], "note": seg["note_high"], "f_target": seg["f555_hz"],
                     "f_sim": round(f_sim, 2), "model_err_cents": round(1200 * math.log2(f_sim / f_model), 2),
                     "err_pct": round(100 * (f_sim / seg["f555_hz"] - 1), 3)})
    # the model drives the tolerance analysis, so it must match the circuit sim closely
    spread = max(r["model_err_cents"] for r in rows) - min(r["model_err_cents"] for r in rows)
    return {"rows": rows, "model_spread_cents": round(spread, 2), "worst_err_pct": max(abs(r["err_pct"]) for r in rows),
            "pass": spread < 2.0}


def sim_tolerance():
    """Two-point calibrated tuning accuracy with 1 % resistors / 2.5 % C_T (Monte Carlo from calc_ladder)."""
    mc = LADDER["monte_carlo_1pct"]
    return {**mc, "pass": mc["calibration_failures"] == 0 and mc["worst_key_cents_p95"] < 5.0}


def lfo_netlist(r_rate):
    # LM358 at 5 V: output swings ~0.02..3.5 V
    opamp = "V = 1.76 + 1.74*tanh(2e4*(v({p})-v({n})))"
    return f"""* LFO: LM358 relaxation oscillator + follower + depth network into 555 CV
VDD vdd 0 DC {VDD}
Rh1 vdd p {LFO_R_HYST}
Rh2 p 0 {LFO_R_HYST}
Rh3 oa p {LFO_R_HYST}
Boa oai 0 {opamp.format(p='p', n='n')}
Roa oai oa 50
Rrate oa n {r_rate}
Clfo n 0 {LFO_C} IC=2.2
Bob obi 0 {opamp.format(p='n', n='ob')}
Rob obi ob 50
C1 ob pt 22u
Rdepth_top pt w 1
Rdepth_bot w 0 10k
Rvs w vs {R_SERIES_VIB}
C2 vs cv 47u
Re1 vdd cv {CV_R_TOP}
Re2 cv 0 {CV_R_BOT}
Ri1 vdd cv {R_INT_555}
Ri2 cv 0 {2 * R_INT_555}
Ccv cv 0 10n
.tran 1m 6 0 1m uic
"""


def sim_lfo(ng):
    res = {}
    for label, r in (("min_rate_R", LFO_R_FIXED + LFO_R_TRIM), ("mid", LFO_R_FIXED + LFO_R_TRIM / 2),
                     ("max_rate_R", LFO_R_FIXED)):
        ng.run(lfo_netlist(r))
        t, vn, vcv = ng.vec("time"), ng.vec("n"), ng.vec("cv")
        sel = t > 3.0  # after the coupling capacitors settle
        edges = rising_edges(t[sel], vn[sel], float(np.mean(vn[sel])))
        f = 1.0 / np.mean(np.diff(edges)) if len(edges) > 2 else 0.0
        dv = (vcv[sel].max() - vcv[sel].min()) / 2
        res[label] = {"R": r, "f_hz": round(f, 2), "cv_dev_v": round(dv, 4), "cv_mean_v": round(float(np.mean(vcv[sel])), 4)}
    rates = [v["f_hz"] for v in res.values()]
    res["pass"] = min(rates) <= 5.0 and max(rates) >= 7.0
    return res


def sim_vibrato_depth(ng, cv_dev):
    """555 pitch swing for the full-depth CV deviation, at the middle key."""
    seg = LADDER["segments"][10]
    vc0 = LADDER["vc_nominal_v"]
    r = seg["r_cum_nominal_ohm"] + R_STYLUS
    f0 = measure_freq(ng, tlc555_ladder(r, vcv_force=vc0))
    f_hi = measure_freq(ng, tlc555_ladder(r, vcv_force=vc0 - cv_dev))
    f_lo = measure_freq(ng, tlc555_ladder(r, vcv_force=vc0 + cv_dev))
    cents = 1200 * math.log2(f_hi / f_lo) / 2
    return {"f0": round(f0, 2), "f_hi": round(f_hi, 2), "f_lo": round(f_lo, 2),
            "depth_cents_pk": round(cents, 1), "pass": 25 <= cents <= 80}


def sim_audio_path(ng):
    """AC response of 4040 -> 100k -> tone cap -> 100n -> A10k pot (max) -> LM386 input (50k)."""
    out = {}
    for tone, c in (("bright", "1p"), ("soft", C_TONE_SOFT)):
        ng.run(f"""* audio path
Vin in 0 DC 0 AC 1
Rser in tn {R_AUDIO_SERIES}
Ctone tn 0 {c}
Cc tn pt 100n
Rpot pt 0 10k
Rin386 pt 0 50k
.ac dec 50 5 50k
""")
        f = np.real(ng.vec("frequency"))
        mag = np.abs(ng.vec("pt"))
        def at(freq):
            return float(np.interp(freq, f, mag))
        peak = mag.max()
        fc_lo = float(f[np.argmax(mag >= peak / math.sqrt(2))])
        above = np.nonzero((mag < peak / math.sqrt(2)) & (f > f[np.argmax(mag)]))[0]
        fc_hi = float(f[above[0]]) if len(above) else float(f[-1])
        out[tone] = {"gain_1k": round(at(1e3), 4), "fc_low_hz": round(fc_lo, 1), "fc_high_hz": round(fc_hi, 1)}
    # 5 Vpp square -> fundamental 3.18 V pk; LM386 gain 20 at 9 V clips near 3.5 V pk output
    vin_pk = 4 / math.pi * 2.5 * out["bright"]["gain_1k"]
    out["lm386_out_pk_full_volume"] = round(vin_pk * 20, 2)
    out["pass"] = 2.0 <= out["lm386_out_pk_full_volume"] <= 3.8 and out["bright"]["fc_low_hz"] < 40
    return out


def main():
    ng = NgSpice()
    results = {}
    print("ladder oscillator ...")
    results["ladder"] = sim_ladder(ng)
    results["tolerance"] = sim_tolerance()
    print("LFO ...")
    results["lfo"] = sim_lfo(ng)
    results["vibrato"] = sim_vibrato_depth(ng, results["lfo"]["mid"]["cv_dev_v"])
    print("audio path ...")
    results["audio"] = sim_audio_path(ng)
    (Path(__file__).parent / "results.json").write_text(json.dumps(results, indent=2, default=lambda o: o.item()))

    lad = results["ladder"]
    print("\nkey note  target_Hz   sim_Hz   err%  sim-vs-model(cents)")
    for r in lad["rows"]:
        print(f"{r['key']:>3} {r['note']:<4} {r['f_target']:>9.2f} {r['f_sim']:>8.2f} {r['err_pct']:>6.2f} "
              f"{r['model_err_cents']:>8.2f}")
    print(f"\nladder sim-vs-model spread {lad['model_spread_cents']} cents -> {'PASS' if lad['pass'] else 'FAIL'}")
    tol = results["tolerance"]
    print(f"calibrated tuning (1% R, 2.5% C): worst key p95 {tol['worst_key_cents_p95']} cents, "
          f"max {tol['worst_key_cents_max']} -> {'PASS' if tol['pass'] else 'FAIL'}")
    print(f"LFO {json.dumps({k: v for k, v in results['lfo'].items() if k != 'pass'})} -> "
          f"{'PASS' if results['lfo']['pass'] else 'FAIL'}")
    print(f"vibrato full depth {results['vibrato']['depth_cents_pk']} cents pk -> "
          f"{'PASS' if results['vibrato']['pass'] else 'FAIL'}")
    print(f"audio {json.dumps({k: v for k, v in results['audio'].items() if k != 'pass'})} -> "
          f"{'PASS' if results['audio']['pass'] else 'FAIL'}")
    all_pass = all(v.get("pass", True) for v in results.values())
    print("\nOVERALL:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
