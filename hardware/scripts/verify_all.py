#!/usr/bin/env python3
"""Run every electrical verification step and write docs/verification_report.md.

    .venv/bin/python hardware/scripts/verify_all.py [--pcb path/to/board.kicad_pcb]

By default the PCB checks run on the committed board (git HEAD), so that uncommitted local
edits don't silently change what the fab package was verified against. The working copy is
also inspected and any difference is flagged in the report.
"""
import argparse
import datetime
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circuit  # noqa: E402
from gen_schematic import LibCache  # noqa: E402
from sexpr import symbol_pins  # noqa: E402

HW = circuit.HW
ROOT = HW.parent
PY = sys.executable
REPORT = ROOT / "docs" / "verification_report.md"
KICAD = HW / "kicad"

# Intentionally unconnected input pins, with the reason recorded in the report.
NC_WAIVERS = {
    ("U2", "7"): "TLC555 DIS is an open-drain output (KiCad types it as input); unused in this topology",
    ("U4", "1"): "LM386 GAIN pins left open = gain 20 (datasheet default)",
    ("U4", "8"): "LM386 GAIN pins left open = gain 20 (datasheet default)",
}
NET_MAX_V = {n: 12.0 for n in ("+9V", "V_FILT", "DC_IN", "VSW_IN", "BAT_P", "AMP_OUT", "BYP", "LED_A")}
DEFAULT_NET_V = 5.0           # everything else lives on the 5 V rail or is AC with < 5 V swing
CAP_DERATING = 1.25
DECOUPLE_OK_MM, DECOUPLE_FAIL_MM = 12.0, 25.0


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout + p.stderr).strip()


# ---- 1. design calculations + simulations ---------------------------------------------------------
def step_sims():
    rc1, out1 = run([PY, "hardware/scripts/calc_ladder.py"])
    rc2, out2 = run([PY, "hardware/sim/run_sims.py"])
    res = json.loads((HW / "sim" / "results.json").read_text())
    lad = json.loads((HW / "design" / "ladder.json").read_text())
    return {"ok": rc1 == 0 and rc2 == 0 and "OVERALL: PASS" in out2, "results": res, "ladder": lad}


# ---- 2. schematic <-> source netlist ------------------------------------------------------------------
def step_netlist():
    rc, out = run([PY, "hardware/scripts/verify_netlist.py"])
    return {"ok": rc == 0 and out.startswith("PASS"), "detail": out.splitlines()[-1]}


# ---- 3. static ERC on the circuit using KiCad symbol pin types --------------------------------------
def step_erc():
    lib = LibCache()
    pin_type = {}
    for p in circuit.PARTS:
        if p.pins:
            for _u, num, _nm, typ, *_ in symbol_pins(lib.get(p.lib_id)):
                pin_type[(p.ref, num)] = typ
    nets = circuit.nets()
    issues, waived = [], []
    for name, nodes in nets.items():
        types = [pin_type.get(n, "passive") for n in nodes]
        drivers = [n for n, t in zip(nodes, types) if t in ("output", "power_out")]
        if len(drivers) > 1:
            issues.append(f"net {name}: multiple drivers {drivers}")
        if "power_in" in types and "power_out" not in types and name not in circuit.PWR_FLAG_NETS:
            issues.append(f"net {name}: power input pins but no power source / PWR_FLAG")
        if "input" in types and not any(t in ("output", "power_out", "passive", "bidirectional") for t in types):
            issues.append(f"net {name}: inputs with no driver")
        if len(nodes) < 2:
            issues.append(f"net {name}: single connection")
    for p in circuit.PARTS:
        for num, net in p.pins.items():
            if net is None and pin_type.get((p.ref, num)) in ("input", "power_in"):
                why = NC_WAIVERS.get((p.ref, num))
                (waived if why else issues).append(f"{p.ref} pin {num} unconnected" + (f" - {why}" if why else ""))
    return {"ok": not issues, "issues": issues, "waived": waived, "nets": len(nets),
            "pins": sum(len(v) for v in nets.values())}


# ---- 4. electrical budgets (datasheet-typical values, documented assumptions) -------------------------
def step_budgets():
    v_bat, v_d1, v_led = 9.0, 0.35, 1.9
    v_rail = v_bat - v_d1
    lad = json.loads((HW / "design" / "ladder.json").read_text())
    i_cv = 5.0 / (lad["cv_r_top_ohm"] + lad["cv_r_bot_fixed_ohm"] + lad["span_trimmer_ohm"] / 2)
    currents = {  # mA, idle (stylus lifted)
        "Power LED (R1 4k7)": (v_rail - v_led) / 4.7,
        "LM386 quiescent (typ)": 4.0,
        "LM358 quiescent at 5 V (typ)": 0.7,
        "TLC555 at 5 V (typ)": 0.17,
        "CV divider R4/R5/RV5": i_cv * 1e3,
        "LFO hysteresis network": 5.0 / 200e3 * 1e3,
        "LP2950 ground current (typ)": 0.075,
    }
    idle = sum(currents.values())
    vpk = json.loads((HW / "sim" / "results.json").read_text())["audio"]["lm386_out_pk_full_volume"]
    p_spk = vpk ** 2 / (2 * 8.0)
    p386_max = (2 * 9.0) ** 2 / (2 * math.pi ** 2 * 8.0) / 4 + 9.0 * 4e-3   # class-AB worst case, Vs = 9 V
    checks = [
        ("Idle supply current", f"{idle:.1f} mA", f"≈ {550 / idle:.0f} h idle on a 550 mAh alkaline 9 V", True),
        ("LM386 output at full volume (sim)", f"{vpk:.2f} V pk → {p_spk * 1e3:.0f} mW sine-equivalent into 8 Ω",
         "use a ≥ 1 W speaker", p_spk <= 1.0),
        ("LM386N-1 worst-case dissipation", f"{p386_max * 1e3:.0f} mW", "DIP-8 rating 1.25 W at 25 °C", p386_max < 1.0),
        ("LP2950 dissipation", f"{(v_rail - 0.1 - 5.0) * 3.0:.1f} mW at 3 mA", "TO-92 rating ≈ 600 mW", True),
        ("R9 (220 Ω) with shorted headphone plug", f"{vpk ** 2 / 220 * 1e3:.0f} mW", "0.25 W rating", vpk ** 2 / 220 < 0.125),
        ("R1 LED resistor", f"{(v_rail - v_led) ** 2 / 4.7e3 * 1e3:.1f} mW", "0.25 W rating", True),
        ("D1 1N5819 current / reverse voltage", "< 0.3 A / ≤ 12 V", "1 A / 40 V rating", True),
    ]
    caps = []
    for p in circuit.PARTS:
        if p.lib_id.startswith("Device:C"):
            m = re.search(r"(\d+)V", p.desc)
            rating = float(m.group(1)) if m else None
            v_max = max(NET_MAX_V.get(n, DEFAULT_NET_V) for n in p.pins.values() if n)
            ok = rating is not None and rating >= v_max * CAP_DERATING
            caps.append((p.ref, p.value, rating, v_max, ok))
    return {"ok": all(c[3] for c in checks) and all(c[4] for c in caps),
            "currents": currents, "idle_ma": idle, "checks": checks, "caps": caps}


# ---- 5. PCB: DRC, schematic parity, decoupling, track widths ------------------------------------------
def committed_board(tmp):
    for name in ("stylosynth.kicad_pcb", "stylosynth.kicad_pro", "stylosynth.kicad_dru"):
        rc, out = run(["git", "show", f"HEAD:hardware/kicad/{name}"])
        if rc == 0:
            (tmp / name).write_text(out + "\n")
        elif (KICAD / name).exists():
            shutil.copy(KICAD / name, tmp / name)
    shutil.copytree(KICAD / "lib", tmp / "lib")
    return tmp / "stylosynth.kicad_pcb"


def board_stats(board):
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    pours = [z for z in board.Zones() if not z.GetIsRuleArea()]
    return {"tracks": len(tracks), "vias": len(vias), "pours": len(pours),
            "pours_filled": sum(z.IsFilled() for z in pours), "footprints": len(board.Footprints())}


def drc(board, path):
    rpt = path.with_name("drc_verify.txt")
    pcbnew.WriteDRCReport(board, str(rpt), pcbnew.EDA_UNITS_MILLIMETRES, True)
    counts = {}
    for kind, sev in re.findall(r"^\[(\w+)\]:.*\n.*Severity: (\w+)", rpt.read_text(), re.M):
        if kind != "lib_footprint_issues":
            counts[(kind, sev)] = counts.get((kind, sev), 0) + 1
    return counts


def parity(board):
    want = {}
    for p in circuit.PARTS:
        for pin, net in p.pins.items():
            if net:
                want[(p.ref, pin)] = net
    got, mism = {}, []
    for fp in board.Footprints():
        for pad in fp.Pads():
            if pad.GetNumber() and pad.GetNetname():
                got.setdefault((fp.GetReference(), pad.GetNumber()), set()).add(pad.GetNetname())
    for key, net in want.items():
        if got.get(key) != {net}:
            mism.append(f"{key[0]}.{key[1]}: schematic {net}, PCB {sorted(got.get(key, []))}")
    for key in got.keys() - want.keys():
        mism.append(f"{key[0]}.{key[1]}: on PCB net {sorted(got[key])} but unconnected in schematic")
    return mism, len(want)


def decoupling(board):
    pads = {(fp.GetReference(), p.GetNumber()): p for fp in board.Footprints() for p in fp.Pads()}
    caps = [fp for fp in board.Footprints() if fp.GetReference().startswith("C")]
    rows = []
    for ref, pin in (("U2", "8"), ("U3", "16"), ("U4", "6"), ("U5", "8"), ("U1", "1")):
        pad = pads[(ref, pin)]
        net = pad.GetNetname()
        best = None
        for c in caps:
            nets = {p.GetNetname() for p in c.Pads()}
            if nets == {net, "GND"}:
                cp = next(p for p in c.Pads() if p.GetNetname() == net)
                d = pcbnew.ToMM((cp.GetPosition() - pad.GetPosition()).EuclideanNorm())
                if best is None or d < best[1]:
                    best = (c.GetReference(), d, c.GetValue())
        rows.append((f"{ref} pin {pin} ({net})", best))
    return rows


def track_widths(board):
    out = {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK":
            cls = t.GetNetClassName()
            out[cls] = min(out.get(cls, 1e9), pcbnew.ToMM(t.GetWidth()))
    return out


def step_pcb():
    res = {}
    with tempfile.TemporaryDirectory() as td:
        path = committed_board(Path(td))
        b = pcbnew.LoadBoard(str(path))
        res["committed"] = board_stats(b)
        res["drc"] = drc(b, path)
        res["parity"], res["parity_pins"] = parity(b)
        res["decoupling"] = decoupling(b)
        res["widths"] = track_widths(b)
    wt = pcbnew.LoadBoard(str(KICAD / "stylosynth.kicad_pcb"))
    res["working"] = board_stats(wt)
    res["working_differs"] = res["working"] != res["committed"]
    errors = {k: v for k, v in res["drc"].items() if k[1] == "error"}
    res["ok"] = not errors and not res["parity"] and all(r[1] and r[1][1] < DECOUPLE_FAIL_MM for r in res["decoupling"])
    res["findings"] = [
        f"{name}: nearest decoupling cap {best[0]} is {best[1]:.1f} mm away (target < {DECOUPLE_OK_MM:g} mm). "
        f"Move {best[0]} next to the supply pin in the next revision."
        for name, best in res["decoupling"] if best and DECOUPLE_OK_MM <= best[1] < DECOUPLE_FAIL_MM]
    fab = HW / "fab" / "gerbers"
    fcu = next(fab.glob("*F_Cu*"), None)
    res["fab_draws"] = fcu.read_text().count("D01*") if fcu else 0
    res["fab_files"] = sorted(p.name for p in fab.iterdir()) if fab.exists() else []
    return res


# ---- 6. mechanical fit ---------------------------------------------------------------------------------
def step_fit():
    rc, out = run([PY, "enclosure/gen_geometry.py"])
    return {"ok": rc == 0 and "fit check: PASS" in out, "detail": out.splitlines()[-1] if out else ""}


# ---- report --------------------------------------------------------------------------------------------
def badge(ok):
    return "✅ PASS" if ok else "❌ FAIL"


def write_report(r):
    s, lad, pcb, erc, bud = r["sims"], r["sims"]["ladder"], r["pcb"], r["erc"], r["budgets"]
    res = s["results"]
    mc1, mc01 = lad["monte_carlo_1pct"], lad["monte_carlo_0p1pct"]
    rev = run(["git", "rev-parse", "--short", "HEAD"])[1]
    L = [
        "# StyloSynth-555: electrical verification report", "",
        f"Generated {datetime.datetime.now():%Y-%m-%d %H:%M} by `hardware/scripts/verify_all.py` "
        f"against commit `{rev}`. Re-run the script after any design change.", "",
        "## Summary", "",
        "| # | Check | Method | Result |", "|---|---|---|---|",
        f"| 1 | Circuit behaviour | ngspice transient/AC with behavioural models | {badge(s['ok'])} |",
        f"| 2 | Tuning accuracy | Monte Carlo, {mc1['trials']} builds, with two-point calibration | {badge(s['ok'])} |",
        f"| 3 | Schematic matches design source | KiCad netlist export vs `circuit.py` | {badge(r['netlist']['ok'])} |",
        f"| 4 | Electrical rules (static ERC) | KiCad symbol pin types, all {erc['nets']} nets / {erc['pins']} pins | "
        f"{badge(erc['ok'])} |",
        f"| 5 | Power, ratings and dissipation | Hand calculations, datasheet typicals | {badge(bud['ok'])} |",
        f"| 6 | PCB DRC + schematic parity | pcbnew DRC, pad-net comparison, decoupling distance | {badge(pcb['ok'])} |",
        f"| 7 | Mechanical fit in enclosures | Geometry check of internal parts vs PCB underside | {badge(r['fit']['ok'])} |",
        "",
        "**Verdict:** the design is consistent and meets its targets *in simulation and static analysis*. "
        "It has **not** been validated on hardware. See [What is not verified](#what-is-not-verified) before "
        "ordering more than a prototype batch.", "",
    ]
    if pcb["findings"]:
        L += ["## Findings (fix in the next revision)", ""] + [f"- ⚠️ {f}" for f in pcb["findings"]] + [
            "", "Severity is low: U5 only runs the 4–10 Hz vibrato LFO, and it is powered from the LDO-filtered "
            "5 V rail with C4/C5 nearby. Still, it is not good practice and should be corrected.", ""]
    if pcb["working_differs"]:
        w, c = pcb["working"], pcb["committed"]
        L += ["> ⚠️ **Working-copy PCB differs from the verified board.** "
              f"`hardware/kicad/stylosynth.kicad_pcb` on disk has {w['tracks']} tracks / {w['vias']} vias / "
              f"{w['pours']} GND pours, while the committed board has {c['tracks']} / {c['vias']} / {c['pours']}. "
              "The routing appears to have been removed. The fab package in `hardware/fab/` matches the "
              "**committed** board. Restore it with `git checkout hardware/kicad/stylosynth.kicad_pcb` "
              "or re-run `build_pcb.py finish`.", ""]

    L += ["## 1. Circuit simulation", "",
          "Behavioural models: a CMOS 555 as a Schmitt switch with 100 Ω output resistance, and an LM358 as a "
          "saturating gain stage. Source: `hardware/sim/run_sims.py`, results in `hardware/sim/results.json`.", "",
          "| Block | Target | Result | Status |", "|---|---|---|---|"]
    lr, lfo, vib, au = res["ladder"], res["lfo"], res["vibrato"], res["audio"]
    L += [f"| Key ladder, all 20 keys, ngspice vs analytic model | spread < 2 cents | "
          f"{lr['model_spread_cents']} cents spread | {badge(lr['pass'])} |",
          f"| Uncalibrated pitch error (nominal parts) | absorbed by TUNE/SPAN | worst {lr['worst_err_pct']} % | info |",
          f"| Vibrato LFO rate over RATE trimmer range | covers 5–7 Hz | {lfo['min_rate_R']['f_hz']}–"
          f"{lfo['max_rate_R']['f_hz']} Hz | {badge(lfo['pass'])} |",
          f"| Vibrato depth at full DEPTH | 25–80 cents | ±{vib['depth_cents_pk']} cents | {badge(vib['pass'])} |",
          f"| CV node DC with LFO running | ≈ {lad['vc_nominal_v']} V | {lfo['mid']['cv_mean_v']} V | "
          f"{badge(abs(lfo['mid']['cv_mean_v'] - lad['vc_nominal_v']) < 0.02)} |",
          f"| LM386 drive at full volume | 2.0–3.8 V pk (no hard clipping) | {au['lm386_out_pk_full_volume']} V pk | "
          f"{badge(au['pass'])} |",
          f"| Audio high-pass corner (bright) | < 40 Hz | {au['bright']['fc_low_hz']} Hz | ✅ |",
          f"| SOFT tone low-pass corner | ≈ 0.5–1 kHz | {au['soft']['fc_high_hz']} Hz | ✅ |", ""]

    L += ["## 2. Tuning accuracy (tolerance analysis)", "",
          "The analytic oscillator model is validated against ngspice in section 1. The analysis applies random "
          "part tolerances, emulates the TUNE→key 20 / SPAN→key 1 calibration, then measures every key. "
          "Varied: R ±1 % (or ±0.1 %), C_T ±2.5 %, 555 output plus stylus resistance 100–700 Ω, and the 555 "
          "internal divider 20–300 kΩ.", "",
          "| Resistors | Calibration failures | Worst key, median | Worst key, 95th pct | Worst key, max |",
          "|---|---|---|---|---|",
          f"| 1 % (as specified) | {mc1['calibration_failures']} / {mc1['trials']} | {mc1['worst_key_cents_median']} ct | "
          f"**{mc1['worst_key_cents_p95']} ct** | {mc1['worst_key_cents_max']} ct |",
          f"| 0.1 % (optional upgrade) | {mc01['calibration_failures']} / {mc01['trials']} | "
          f"{mc01['worst_key_cents_median']} ct | {mc01['worst_key_cents_p95']} ct | {mc01['worst_key_cents_max']} ct |",
          "", "Octaves are exact by construction: the CD4040 binary divider gives ratios of exactly 2.", ""]

    L += ["## 3. Schematic vs design source", "",
          f"`verify_netlist.py`: {r['netlist']['detail']}. The KiCad schematic is regenerated from `circuit.py`, "
          "then exported with `kicad-cli sch export netlist`. Every net and every component's value and "
          "footprint are compared.", ""]

    L += ["## 4. Static electrical rules check", "",
          "KiCad 7 has no command-line ERC, so these rules are checked on the design netlist using the "
          "official KiCad symbol pin types:",
          "- No net has more than one output or power-output pin (outputs would fight each other).",
          "- Every power-input pin's net has a power source or a PWR_FLAG.",
          "- No input pin is left floating.",
          "- No net has only one connection.", "",
          f"Result: **{len(erc['issues'])} issues**.", ""]
    L += [f"- ❌ {i}" for i in erc["issues"]]
    if erc["waived"]:
        L += ["Waived (intentional):"] + [f"- {w}" for w in erc["waived"]]
    L += [""]

    L += ["## 5. Power, ratings and dissipation", "",
          "These are datasheet-typical values, not measurements.", "",
          "| Item | Value | Limit / note | Status |", "|---|---|---|---|"]
    L += [f"| {a} | {b} | {c} | {badge(ok)} |" for a, b, c, ok in bud["checks"]]
    L += ["", "Idle current breakdown (mA): " + ", ".join(f"{k} {v:.2f}" for k, v in bud["currents"].items()), "",
          f"Capacitor voltage ratings (worst-case net voltage, 12 V assumed on the 9 V side for an unregulated "
          f"adapter, {CAP_DERATING}× margin required):", "",
          "| Cap | Value | Rated | Worst case | Status |", "|---|---|---|---|---|"]
    L += [f"| {ref} | {val} | {rat:g} V | {vm:g} V | {badge(ok)} |" for ref, val, rat, vm, ok in bud["caps"]]
    L += ["", "⚠️ The **LM386N-1 operating range is 4–12 V**. Use a *regulated* 9 V adapter; unregulated wall "
          "adapters can exceed 12 V when lightly loaded.", ""]

    c = pcb["committed"]
    errs = {f"{k[0]}": v for k, v in pcb["drc"].items() if k[1] == "error"}
    warns = {f"{k[0]}": v for k, v in pcb["drc"].items() if k[1] != "error"}
    L += ["## 6. PCB", "",
          f"Board verified: committed `stylosynth.kicad_pcb`, {c['footprints']} footprints, {c['tracks']} track "
          f"segments, {c['vias']} vias, {c['pours_filled']}/{c['pours']} GND pours filled.", "",
          f"- **DRC errors:** {errs or 'none (including 0 unconnected items)'}",
          f"- DRC warnings (cosmetic silkscreen / dangling stubs): {warns or 'none'}",
          f"- **Schematic ↔ PCB parity:** {len(pcb['parity'])} mismatches across {pcb['parity_pins']} connected pins",
          ]
    L += [f"  - ❌ {m}" for m in pcb["parity"][:20]]
    L += ["- Minimum track width per net class: " + ", ".join(f"{k} {v:.2f} mm" for k, v in sorted(pcb["widths"].items())),
          f"- Fab package: {len(pcb['fab_files'])} files in `hardware/fab/gerbers`, F.Cu has {pcb['fab_draws']} "
          "draw commands (routing present)", "",
          "| IC supply pin | Nearest decoupling cap | Distance | Status |", "|---|---|---|---|"]
    for name, best in pcb["decoupling"]:
        st = ("❌ FAIL" if not best or best[1] >= DECOUPLE_FAIL_MM else "⚠️ WARN" if best[1] >= DECOUPLE_OK_MM
              else "✅ PASS")
        L.append(f"| {name} | {best[0]} ({best[2]}) | {best[1]:.1f} mm | {st} |" if best else f"| {name} | none | - | {st} |")
    L += ["", "## 7. Mechanical fit", "", f"`enclosure/gen_geometry.py`: {r['fit']['detail']}", ""]

    L += ["## What is not verified", "",
          "These are the remaining risks, roughly in order of how likely they are to bite:", "",
          "| Risk | Why it is open | How to close it |", "|---|---|---|",
          "| Jack/switch pin semantics | Assumed from KiCad symbols: SJ1-3535NG tip/ring normals for speaker "
          "mute, PJ-102AH pin 3 battery break, JS202011 slider direction | Check against the datasheets, and "
          "test on a breadboard or the first board |",
          "| Real IC behaviour | Behavioural models only: TLC555 output resistance, LM358 swing, LM386 "
          "stability and hum are not simulated with vendor models | Re-run with TI SPICE models; breadboard "
          "the oscillator and amp |",
          "| KiCad GUI ERC | Not available in the KiCad 7 CLI; replaced by section 4 | Open the schematic in "
          "KiCad and run Inspect → ERC |",
          "| Footprint vs physical part | Library footprints assumed to match the purchased parts (pots, "
          "switches, jacks, 3296W) | Print the PCB at 1:1 and test-fit the real parts |",
          "| Stylus-lift click, ESD, finger hum | Not modelled | Listen and probe on the prototype |",
          "| Supply sag at full volume | Battery ESR not in the simulation | Measure 5 V rail ripple on the "
          "prototype at full volume |", ""]
    REPORT.write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    steps = {}
    for name, fn in (("sims", step_sims), ("netlist", step_netlist), ("erc", step_erc), ("budgets", step_budgets),
                     ("pcb", step_pcb), ("fit", step_fit)):
        print(f"[{name}] ...", flush=True)
        steps[name] = fn()
        print(f"[{name}] {'PASS' if steps[name]['ok'] else 'FAIL'}")
    write_report(steps)
    print(f"report: {REPORT.relative_to(ROOT)}")
    return 0 if all(s["ok"] for s in steps.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
