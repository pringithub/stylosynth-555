#!/usr/bin/env python3
"""Build the LaTeX design & verification report (docs/report/StyloSynth-555_Report.pdf).

    .venv/bin/python docs/report/build_report.py

Re-runs the verification steps for live data, generates vector figures (matplotlib + ngspice),
exports schematic/PCB plots from the committed board, writes report.tex and compiles it with
Tectonic (tools/tectonic). Requires the proxy for Tectonic's first package download.
"""
import csv
import datetime
import math
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hardware" / "scripts"))
sys.path.insert(0, str(ROOT / "hardware" / "sim"))
import calc_ladder  # noqa: E402
import run_sims  # noqa: E402
import verify_all  # noqa: E402
from build_pcb import BOARD_H, BOARD_W, ORIGIN  # noqa: E402
from ngspice import NgSpice, rising_edges  # noqa: E402

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
TECTONIC = ROOT / "tools" / "tectonic"
PDF_NAME = "StyloSynth-555_Report.pdf"

plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
                     "figure.dpi": 150, "savefig.bbox": "tight", "axes.spines.top": False,
                     "axes.spines.right": False, "pdf.fonttype": 42})
BLUE, ORANGE, GREEN, RED, GREY = "#1f5fa8", "#e07b1a", "#2a9d4b", "#c0392b", "#777777"
W_FULL, W_HALF = 6.3, 3.1

UNICODE_TEX = {"±": r"$\pm$", "Ω": r"$\Omega$", "≈": r"$\approx$", "°": r"$^\circ$", "→": r"$\rightarrow$",
               "×": r"$\times$", "≥": r"$\geq$", "≤": r"$\leq$", "µ": r"$\mu$", "↔": r"$\leftrightarrow$",
               "≥": r"$\geq$", "⚠️": "", "✅": "", "❌": "", "…": r"\ldots{}", "—": "---"}


def tex(s):
    s = str(s)
    out = []
    for ch in s:
        if ch in "\\":
            out.append(r"\textbackslash{}")
        elif ch in "&%$#_{}":
            out.append("\\" + ch)
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        else:
            out.append(ch)
    s = "".join(out)
    for k, v in UNICODE_TEX.items():
        s = s.replace(k, v)
    return s


def status(ok):
    return r"\pass" if ok else r"\fail"


# ---- data collection ----------------------------------------------------------------------------
def collect():
    print("running verification steps ...", flush=True)
    steps = {name: fn() for name, fn in (("sims", verify_all.step_sims), ("netlist", verify_all.step_netlist),
                                         ("erc", verify_all.step_erc), ("budgets", verify_all.step_budgets),
                                         ("pcb", verify_all.step_pcb), ("fit", verify_all.step_fit))}
    for k, v in steps.items():
        print(f"  {k}: {'PASS' if v['ok'] else 'FAIL'}")
    return steps


def monte_carlo_per_key(lad, trials=2000, r_tol=0.01, c_tol=0.025, seed=1):
    """Same random sequence as calc_ladder.monte_carlo, but keeps every key's error."""
    fixed = [s["r_fixed_ohm"] for s in lad["segments"]]
    targets = [s["f555_hz"] for s in lad["segments"]]
    rng = random.Random(seed)
    errs = []
    for _ in range(trials):
        c = calc_ladder.C_T * (1 + rng.uniform(-c_tol, c_tol))
        r0 = rng.uniform(100, 700)
        r_int = rng.uniform(20e3, 300e3)
        tol = [rng.uniform(-r_tol, r_tol) for _ in fixed]
        cal = calc_ladder.calibrate(fixed, targets, c, r0, tol, r_int)
        if cal is None:
            continue
        fs = calc_ladder.ladder_freqs(fixed, *cal, c, r0, tol, r_int)
        errs.append([1200 * math.log2(f / t) for f, t in zip(fs, targets)])
    return np.array(errs)[:, ::-1]          # key 1 .. key 20


# ---- figures --------------------------------------------------------------------------------------
def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.pdf")
    plt.close(fig)


def fig_note_map(lad):
    segs = sorted(lad["segments"], key=lambda s: s["key"])
    keys = [s["key"] for s in segs]
    fig, ax = plt.subplots(figsize=(W_FULL, 2.6))
    colors = {"BASS": GREY, "LOW": GREEN, "MID": BLUE, "HIGH": ORANGE}
    for pos, col in colors.items():
        ax.plot(keys, [s["freqs_hz"][pos] for s in segs], "o-", ms=3, color=col,
                label=f"{pos} (÷{lad['dividers'][pos]})")
    ax.set_yscale("log")
    ax.set_xticks(keys)
    ax.set_xticklabels([s["notes"]["MID"][:-1] for s in segs], fontsize=7)
    ax.set_xlabel("Key (note name)")
    ax.set_ylabel("Frequency (Hz)")
    ax.legend(ncol=4, fontsize=7, loc="upper left")
    ax.set_title("Note map: 20 keys × 4 octave settings (exact ×2 steps from the CD4040)")
    save(fig, "note_map")


def fig_ladder(lad, sims):
    rows = sorted(sims["ladder"]["rows"], key=lambda r: r["key"])
    segs = sorted(lad["segments"], key=lambda s: s["key"])
    keys = [r["key"] for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W_FULL, 2.4))
    a1.bar(keys, [s["r_fixed_ohm"] / 1e3 if s["segment"] else 0 for s in segs], color=BLUE, width=0.7)
    a1.set_xlabel("Key")
    a1.set_ylabel("Segment resistor (kΩ)")
    a1.set_title("Ladder segments (E96, R102–R120)")
    a1.set_xticks(keys[::2])
    a2.plot(keys, [r["model_err_cents"] for r in rows], "o-", color=ORANGE, ms=3, label="ngspice − analytic model")
    a2.plot(keys, [1200 * math.log2(r["f_sim"] / r["f_target"]) for r in rows], "s-", color=BLUE, ms=3,
            label="ngspice − target (uncalibrated)")
    a2.axhline(0, color="k", lw=0.6)
    a2.set_xlabel("Key")
    a2.set_ylabel("Error (cents)")
    a2.set_title("Nominal pitch error before calibration")
    a2.set_xticks(keys[::2])
    a2.legend(fontsize=6.5)
    fig.tight_layout()
    save(fig, "ladder")


def fig_monte_carlo(errs1, errs01):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W_FULL, 2.5), gridspec_kw={"width_ratios": [1.6, 1]})
    a1.boxplot(errs1, positions=range(1, 21), widths=0.6, whis=(2.5, 97.5), showfliers=False,
               medianprops={"color": ORANGE}, boxprops={"color": BLUE}, whiskerprops={"color": BLUE},
               capprops={"color": BLUE})
    a1.axhspan(-5, 5, color=GREEN, alpha=0.08, label="±5 cents")
    a1.set_xlabel("Key")
    a1.set_ylabel("Error after calibration (cents)")
    a1.set_title("Per-key error, 1 % resistors (box: IQR, whiskers: 95 %)")
    a1.set_xticks(range(1, 21))
    a1.set_xticklabels([str(k) if k % 2 else "" for k in range(1, 21)])
    a1.legend(fontsize=7, loc="upper right")
    w1, w01 = np.abs(errs1).max(axis=1), np.abs(errs01).max(axis=1)
    bins = np.linspace(0, max(w1.max(), w01.max()) * 1.05, 30)
    a2.hist(w1, bins=bins, color=BLUE, alpha=0.7, label="1 % resistors")
    a2.hist(w01, bins=bins, color=ORANGE, alpha=0.7, label="0.1 % resistors")
    a2.axvline(np.percentile(w1, 95), color=BLUE, ls="--", lw=1)
    a2.set_xlabel("Worst key per build (cents)")
    a2.set_ylabel("Builds")
    a2.set_title(f"{len(w1)} simulated builds")
    a2.legend(fontsize=7)
    fig.tight_layout()
    save(fig, "monte_carlo")


def fig_555(ng, lad):
    seg = lad["segments"][10]
    ng.run(run_sims.tlc555_ladder(seg["r_cum_nominal_ohm"] + run_sims.R_STYLUS))
    t, th, out = ng.vec("time"), ng.vec("th"), ng.vec("out")
    edges = rising_edges(t, out, 2.5)
    sel = (t >= edges[1]) & (t <= edges[4])
    t0 = edges[1]
    fig, ax = plt.subplots(figsize=(W_FULL, 2.2))
    ax.plot((t[sel] - t0) * 1e3, out[sel], color=GREY, lw=1, label="555 output (pin 3)")
    ax.plot((t[sel] - t0) * 1e3, th[sel], color=BLUE, lw=1.4, label="timing capacitor (pins 2/6)")
    vc = lad["vc_nominal_v"]
    for v, txt in ((vc, "$V_{CV}$"), (vc / 2, "$V_{CV}/2$")):
        ax.axhline(v, color=ORANGE, ls="--", lw=0.8)
        ax.text(0.02, v + 0.08, txt, color=ORANGE, fontsize=8)
    f = 1 / np.mean(np.diff(edges[1:]))
    ax.set_title(f"TLC555 with the ladder at key {seg['key']} ({seg['note_high']} at HIGH): f = {f:.1f} Hz")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Voltage (V)")
    ax.legend(fontsize=7, loc="right")
    save(fig, "osc_555")


def fig_lfo(ng, lad):
    ng.run(run_sims.lfo_netlist(run_sims.LFO_R_FIXED + run_sims.LFO_R_TRIM / 2))
    t, vn, oa, cv = ng.vec("time"), ng.vec("n"), ng.vec("oa"), ng.vec("cv")
    sel = (t > 3.0) & (t < 3.75)
    tt = (t[sel] - 3.0) * 1e3
    vc = cv[sel]
    cents = 1200 * np.log2(np.array([calc_ladder.period_factor(lad["vc_nominal_v"]) / calc_ladder.period_factor(v)
                                     for v in vc]))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(W_FULL, 3.4), sharex=True)
    a1.plot(tt, oa[sel], color=GREY, lw=1, label="LM358A output (square)")
    a1.plot(tt, vn[sel], color=BLUE, lw=1.4, label="timing cap (triangle-like LFO)")
    a1.set_ylabel("Voltage (V)")
    a1.legend(fontsize=7, loc="right")
    a1.set_title("Vibrato LFO (RATE trimmer mid-travel) and resulting pitch modulation at full DEPTH")
    a2.plot(tt, cents, color=ORANGE, lw=1.4)
    a2.axhline(float(np.mean(cents)), color=GREY, ls="--", lw=0.8)
    a2.set_ylabel("Pitch deviation (cents)")
    a2.set_xlabel("Time (ms)")
    save(fig, "lfo")
    return {"mean": float(np.mean(cents)), "min": float(cents.min()), "max": float(cents.max())}


def fig_audio(ng):
    fig, ax = plt.subplots(figsize=(W_HALF + 0.4, 2.4))
    for tone, c, col in (("bright", "1p", BLUE), ("soft", run_sims.C_TONE_SOFT, ORANGE)):
        ng.run(f"""* audio path
Vin in 0 DC 0 AC 1
Rser in tn {run_sims.R_AUDIO_SERIES}
Ctone tn 0 {c}
Cc tn pt 100n
Rpot pt 0 10k
Rin386 pt 0 50k
.ac dec 50 5 50k
""")
        f, mag = np.real(ng.vec("frequency")), np.abs(ng.vec("pt"))
        ax.semilogx(f, 20 * np.log10(mag), color=col, lw=1.4, label=tone.upper())
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Gain to LM386 input (dB)")
    ax.set_title("Tone switch response (volume max)")
    ax.legend(fontsize=7)
    save(fig, "audio")


def fig_lfo_rate(sims):
    lfo = sims["lfo"]
    pts = sorted((v["R"] / 1e3, v["f_hz"]) for k, v in lfo.items() if isinstance(v, dict))
    fig, ax = plt.subplots(figsize=(W_HALF - 0.2, 2.4))
    ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", color=BLUE)
    ax.axhspan(5, 7, color=GREEN, alpha=0.1, label="classic 5–7 Hz")
    ax.set_xlabel("R13 + RATE trimmer (kΩ)")
    ax.set_ylabel("LFO rate (Hz)")
    ax.set_title("Vibrato rate range")
    ax.legend(fontsize=7)
    save(fig, "lfo_rate")


def fig_power(bud):
    items = sorted(bud["currents"].items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(W_FULL, 2.0))
    ax.barh([k for k, _ in items], [v for _, v in items], color=BLUE)
    for i, (_, v) in enumerate(items):
        ax.text(v + 0.05, i, f"{v:.2f} mA", va="center", fontsize=7)
    ax.set_xlabel("Idle current (mA)")
    ax.set_title(f"Idle supply budget: {bud['idle_ma']:.1f} mA total (stylus lifted)")
    ax.tick_params(axis="y", labelsize=7)
    save(fig, "power")


def board_plots(tmp):
    """Vector PCB plots from the committed (routed) board; returns trim margins for \\includegraphics."""
    pcb = verify_all.committed_board(Path(tmp))
    plots = {"pcb_front": "F.Cu,F.SilkS,Edge.Cuts", "pcb_back": "B.Cu,Edge.Cuts",
             "pcb_copper": "F.Cu,B.Cu,Edge.Cuts"}
    for name, layers in plots.items():
        subprocess.run(["kicad-cli", "pcb", "export", "pdf", "--layers", layers, "-o", str(FIG / f"{name}.pdf"),
                        str(pcb)], check=True, capture_output=True)
    m = 2.0
    # kicad-cli plots on an A4 landscape page at absolute board coordinates
    return f"{ORIGIN[0] - m}mm {210 - ORIGIN[1] - BOARD_H - m}mm {297 - ORIGIN[0] - BOARD_W - m}mm {ORIGIN[1] - m}mm"


# ---- LaTeX ----------------------------------------------------------------------------------------
PREAMBLE = r"""
\documentclass[10pt,a4paper]{article}
\usepackage[margin=22mm]{geometry}
\usepackage{fontspec}
\usepackage{microtype,booktabs,longtable,graphicx,float,amsmath,array,xcolor,pdflscape,enumitem}
\usepackage[font=small,labelfont=bf]{caption}
\usepackage{subcaption}
\usepackage{siunitx}
\sisetup{detect-all}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,fit,backgrounds}
\usepackage{fancyhdr}
\usepackage[hidelinks]{hyperref}
\definecolor{ssblue}{HTML}{1F5FA8}\definecolor{ssgreen}{HTML}{2A9D4B}\definecolor{ssred}{HTML}{C0392B}
\definecolor{ssorange}{HTML}{E07B1A}
\newcommand{\pass}{\textcolor{ssgreen}{\textbf{PASS}}}
\newcommand{\fail}{\textcolor{ssred}{\textbf{FAIL}}}
\newcommand{\warn}{\textcolor{ssorange}{\textbf{WARN}}}
\pagestyle{fancy}\fancyhf{}
\lhead{\small StyloSynth-555}\rhead{\small Design \& Verification Report}\cfoot{\small\thepage}
\setlength{\headheight}{14pt}
\setlist{nosep,leftmargin=*}
"""

BLOCK_DIAGRAM = r"""
\begin{figure}[H]\centering
\begin{tikzpicture}[font=\small, node distance=6mm and 9mm,
  blk/.style={draw, rounded corners=2pt, fill=ssblue!8, minimum height=9mm, minimum width=22mm, align=center},
  io/.style={draw, rounded corners=2pt, fill=ssorange!12, minimum height=8mm, align=center},
  pw/.style={draw, rounded corners=2pt, fill=ssgreen!12, minimum height=8mm, align=center},
  ar/.style={-{Stealth[length=2mm]}, thick}]
\node[io] (keys) {20 keys +\\ resistor ladder};
\node[io, below=of keys] (sty) {Stylus};
\node[blk, right=of keys, yshift=-7mm] (osc) {TLC555\\ oscillator};
\node[blk, right=of osc] (div) {CD4040\\ $\div$2/4/8/16};
\node[blk, right=of div] (oct) {OCT-1/OCT-2\\ selector};
\node[blk, below=of oct] (tone) {Tone filter\\ + VOLUME};
\node[blk, left=of tone] (amp) {LM386\\ amplifier};
\node[io, left=of amp] (out) {Speaker /\\ phones};
\node[blk, above=of osc] (lfo) {LM358 LFO\\ RATE, DEPTH};
\node[blk, above=of div] (cal) {TUNE / SPAN\\ calibration};
\node[pw, above=of oct] (pwr) {9\,V batt / DC $\rightarrow$\\ LP2950 5\,V};
\draw[ar] (keys) -- (osc); \draw[ar] (sty) -| (osc);
\draw[ar] (osc) -- (div); \draw[ar] (div) -- (oct); \draw[ar] (oct) -- (tone);
\draw[ar] (tone) -- (amp); \draw[ar] (amp) -- (out);
\draw[ar] (lfo) -- node[left, font=\scriptsize]{CV} (osc); \draw[ar] (cal) -- (osc);
\end{tikzpicture}
\caption{Signal flow. The oscillator, divider and LFO run on a regulated 5\,V rail; the amplifier runs from the raw 9\,V supply.}
\label{fig:block}
\end{figure}
"""


def fig_env(name, caption, width=r"\textwidth", label=None, extra=""):
    lab = f"\\label{{fig:{label or name}}}" if True else ""
    return (f"\\begin{{figure}}[H]\\centering\\includegraphics[width={width}{extra}]{{figures/{name}}}"
            f"\\caption{{{caption}}}{lab}\\end{{figure}}\n")


def table(cols, header, rows, caption=None, size=r"\small", long=False):
    env = "longtable" if long else "tabular"
    head = " & ".join(f"\\textbf{{{h}}}" for h in header) + r" \\ \midrule"
    body = "\n".join(" & ".join(r) + r" \\" for r in rows)
    if long:
        return (f"{{{size}\\begin{{longtable}}{{{cols}}}\\caption{{{caption}}}\\\\\\toprule\n{head}\\endfirsthead\n"
                f"\\toprule {head}\\endhead\n{body}\n\\bottomrule\\end{{longtable}}}}\n")
    cap = f"\\caption{{{caption}}}" if caption else ""
    return (f"\\begin{{table}}[H]\\centering{size}{cap}\\begin{{tabular}}{{{cols}}}\\toprule\n{head}\n{body}\n"
            f"\\bottomrule\\end{{tabular}}\\end{{table}}\n")


def build_tex(st, errs1, errs01, trim, rev, vstat):
    s, lad = st["sims"]["results"], st["sims"]["ladder"]
    pcb, erc, bud, fit = st["pcb"], st["erc"], st["budgets"], st["fit"]
    mc1, mc01 = lad["monte_carlo_1pct"], lad["monte_carlo_0p1pct"]
    all_ok = all(v["ok"] for v in st.values())
    c = pcb["committed"]
    drc_err = sum(v for k, v in pcb["drc"].items() if k[1] == "error")
    drc_warn = {k[0]: v for k, v in pcb["drc"].items() if k[1] != "error"}
    today = datetime.date.today().strftime("%d %B %Y")

    T = [PREAMBLE, r"\begin{document}"]
    T.append(rf"""
\begin{{titlepage}}\centering
\vspace*{{25mm}}
{{\Huge\bfseries StyloSynth-555\par}}\vspace{{4mm}}
{{\Large A 555-based stylus synthesizer\par}}\vspace{{2mm}}
{{\large Design \& Verification Report\par}}\vspace{{10mm}}
\includegraphics[width=0.85\textwidth]{{renders/printed_closeup}}\par\vspace{{10mm}}
{{\large {today}\par}}\vspace{{2mm}}
{{\small Design revision v1.2 \quad$\cdot$\quad commit \texttt{{{rev}}}\par}}
\vfill
\begin{{minipage}}{{0.85\textwidth}}\small
\textbf{{Abstract.}} StyloSynth-555 is a stylophone-style analogue synthesizer with a CMOS 555 oscillator,
a 20-key exposed-copper keyboard, four exact octaves from a binary divider, an LFO vibrato and an LM386
amplifier. It runs on a single 136\,$\times$\,98\,mm two-layer PCB powered from a 9\,V battery. This report
describes the design and presents the automated verification: circuit simulation, a {mc1['trials']}-build
tolerance analysis, schematic/netlist consistency, static electrical-rule checking, power budgets, PCB DRC
and mechanical fit. All {len(st)} verification steps {'pass' if all_ok else 'do not all pass'}. The design has
not yet been validated on hardware.
\end{{minipage}}
\end{{titlepage}}
\tableofcontents\newpage
""")

    T.append(r"\section{Introduction}" + f"""
The instrument is inspired by the vintage Stylophone and by the TouchTone555 project. None of the reference
files are reused; this is an independent design that keeps the feature set and fixes the issues the
reference documented:
\\begin{{itemize}}
\\item \\textbf{{Pitch drift with volume}} $\\rightarrow$ the oscillator gets its own LDO-regulated, RC-filtered
5\\,V rail.
\\item \\textbf{{Inexact octaves from capacitor banks}} $\\rightarrow$ a CD4040 binary divider gives
mathematically exact 2:1 ratios.
\\item \\textbf{{Op-amp unable to drive the speaker}} $\\rightarrow$ an LM386 power amplifier.
\\item \\textbf{{20 tuning trimmers}} $\\rightarrow$ fixed 1\\,\\% resistors plus a two-trimmer (TUNE/SPAN)
calibration, verified statistically in Section~\\ref{{sec:mc}}.
\\end{{itemize}}
The design is fully script-generated. \\texttt{{circuit.py}} is the single source of truth for the
schematic, PCB and BOM, and \\texttt{{verify\\_all.py}} re-runs every check in this report.
""")

    T.append(r"\section{System architecture}" + BLOCK_DIAGRAM + r"""
\begin{itemize}
\item \textbf{Oscillator.} A TLC555 in the 50\,\%-duty topology: the output charges the 22\,nF polypropylene
timing capacitor through the key ladder. The stylus picks a tap, so the timing resistance and the pitch depend
on the key touched. A 10\,M$\Omega$ pull-down silences the oscillator when the stylus is lifted.
\item \textbf{Octaves.} The CD4040 divides by 2, 4, 8 or 16. Two DPDT switches form a 2-bit selector.
\item \textbf{Vibrato.} An LM358 relaxation oscillator (3.9--9.6\,Hz) is buffered and AC-coupled through the
DEPTH pot into the 555 control-voltage pin.
\item \textbf{Audio.} A series resistor and switchable tone capacitor feed the VOLUME pot and an LM386 at
gain 20, with a Zobel network and a 220\,$\mu$F output capacitor. The headphone jack's switch contacts
disconnect the speaker and add a 220\,$\Omega$ series resistor.
\item \textbf{Power.} 9\,V battery or 9\,V centre-negative DC (the jack switch disconnects the battery),
Schottky reverse protection, and an LP2950-5.0 LDO behind a 47\,$\Omega$/100\,$\mu$F filter.
\end{itemize}
""")

    segs = sorted(lad["segments"], key=lambda x: x["key"])
    T.append(r"\section{Circuit design}\subsection{Oscillator and key ladder}" + rf"""
For a rail-to-rail 555 whose thresholds are $V_{{CV}}$ and $V_{{CV}}/2$, the capacitor charges towards
$V_{{DD}}$ and discharges towards 0, so
\begin{{equation}}
f \;=\; \frac{{1}}{{R\,C_T\left[\ln\dfrac{{V_{{DD}}-V_{{CV}}/2}}{{V_{{DD}}-V_{{CV}}}} + \ln 2\right]}},
\qquad R = R_0 + \sum_{{i\le k}} R_i ,
\end{{equation}}
where $R_0$ is the 555 output resistance plus the 100\,$\Omega$ stylus resistor. With
$C_T = {lad['c_t_farad'] * 1e9:g}$\,nF and $V_{{CV}} = {lad['vc_nominal_v']:.3f}$\,V, the 555 spans
{lad['f555_range_hz'][0]:g}--{lad['f555_range_hz'][1]:g}\,Hz. Segment values are chosen greedily from E96 so that
the \emph{{cumulative}} resistance tracks each target, which means rounding errors never accumulate.

\textbf{{Calibration.}} TUNE (RV4, {lad['tune_trimmer_ohm']:g}\,$\Omega$) adds an offset common to all keys and
is set on key 20. SPAN (RV5, {lad['span_trimmer_ohm']:g}\,$\Omega$) sits in the CV divider: it changes
$V_{{CV}}$, which scales every frequency by the same factor, and is set on key 1. Two adjustments cancel the
two dominant unknowns ($R_0$ and the $C_T$ tolerance).
""")
    T.append(fig_env("note_map", "Design frequency of every key at each octave setting."))
    rows = [[str(x["key"]), x["notes"]["MID"], x["r_fixed"].replace("k", "k") if x["segment"] else
             f"{x['r_fixed']} + TUNE", f"{x['f555_hz']:.1f}", f"{x['freqs_hz']['MID']:.1f}"] for x in segs]
    T.append(table("rrrrr", ["Key", "Note (MID)", r"Segment R ($\Omega$)", r"$f_{555}$ (Hz)",
                             "Output, MID (Hz)"], [[tex(v) for v in r] for r in rows],
                   caption="Ladder values (key 20 is fed first from the 555 output).", size=r"\footnotesize"))

    T.append(r"""\subsection{Vibrato, audio and power}
The LFO is a single-supply Schmitt relaxation oscillator with $3\times100$\,k$\Omega$ hysteresis and
$R = 68\,\mathrm{k}\Omega + $ RATE (100\,k$\Omega$) into 1\,$\mu$F; its timing node is buffered by the second
op-amp half. A 1.5\,k$\Omega$\,/\,(2.4\,k$\Omega$ + SPAN) external CV divider swamps the TLC555's internal
divider, so the vibrato depth and the calibration don't depend on the 555's internal resistors. In the audio
path, a 150\,k$\Omega$ series resistor sets the LM386 input so full volume just avoids hard clipping at 9\,V.
""")

    lr, lfo, vib, au = s["ladder"], s["lfo"], s["vibrato"], s["audio"]
    T.append(r"\section{Simulation results}" + r"""
All circuit simulations use ngspice (the KiCad 7 shared library) driven from Python. The 555 is modelled
behaviourally as a CV-referenced Schmitt switch with 100\,$\Omega$ output resistance, and the LM358 as a
saturating high-gain stage (0.02--3.5\,V swing at 5\,V).
""")
    T.append(fig_env("osc_555", "Oscillator transient: the timing capacitor swings between $V_{CV}/2$ and $V_{CV}$."))
    T.append(fig_env("ladder", "Ladder segment values and nominal (uncalibrated) pitch error. The near-constant "
                     "offset between simulation and target is removed by TUNE/SPAN; the simulation agrees with "
                     f"the analytic model to within {lr['model_spread_cents']} cents across all keys."))
    T.append(fig_env("lfo", f"Vibrato LFO waveform and pitch modulation at full DEPTH: {vstat['min']:+.0f} to "
                     f"{vstat['max']:+.0f} cents. The LM358 output swing is asymmetric (0.02--3.5\\,V), so the "
                     f"time-averaged pitch rises by {vstat['mean']:.0f} cents while vibrato is on (dashed line). "
                     "The offset shrinks in proportion to DEPTH; calibration is done with vibrato off."))
    T.append(r"\begin{figure}[H]\centering\begin{subfigure}{0.48\textwidth}\includegraphics[width=\linewidth]"
             r"{figures/lfo_rate}\caption{LFO rate vs. RATE setting}\end{subfigure}\hfill"
             r"\begin{subfigure}{0.5\textwidth}\includegraphics[width=\linewidth]{figures/audio}"
             r"\caption{Tone response into the LM386}\end{subfigure}\caption{Vibrato rate range and audio path."
             r"}\end{figure}")
    rows = [
        ["Ladder: ngspice vs analytic model", "spread < 2 ct", f"{lr['model_spread_cents']} ct", status(lr["pass"])],
        ["LFO rate range", "covers 5--7 Hz", f"{lfo['min_rate_R']['f_hz']}--{lfo['max_rate_R']['f_hz']} Hz",
         status(lfo["pass"])],
        ["Vibrato depth (full)", "25--80 ct", f"±{vib['depth_cents_pk']} ct", status(vib["pass"])],
        ["CV DC with LFO running", f"{lad['vc_nominal_v']:.3f} V", f"{lfo['mid']['cv_mean_v']:.4f} V",
         status(abs(lfo['mid']['cv_mean_v'] - lad['vc_nominal_v']) < 0.02)],
        ["LM386 drive, full volume", "2.0--3.8 V pk", f"{au['lm386_out_pk_full_volume']} V pk", status(au["pass"])],
        ["Audio HPF corner", "< 40 Hz", f"{au['bright']['fc_low_hz']} Hz", status(au['bright']['fc_low_hz'] < 40)],
        ["SOFT LPF corner", "0.5--1 kHz", f"{au['soft']['fc_high_hz']} Hz", status(500 <= au['soft']['fc_high_hz'] <= 1000)],
    ]
    T.append(table("llll", ["Check", "Target", "Result", "Status"], [[tex(r[0]), tex(r[1]), tex(r[2]), r[3]]
                                                                      for r in rows], caption="Simulation checks."))

    w1 = np.abs(errs1).max(axis=1)
    T.append(r"\section{Tolerance analysis}\label{sec:mc}" + rf"""
Each simulated build draws random values for: every ladder resistor ($\pm$1\,\% or $\pm$0.1\,\%), $C_T$
($\pm$2.5\,\%), $R_0$ (100--700\,$\Omega$) and the 555 internal divider (20--300\,k$\Omega$). The two-point
calibration is then emulated (TUNE on key 20, SPAN on key 1, iterated) and the error of every key is
measured. The model behind this is the analytic equation, validated against ngspice in the previous section.
""")
    T.append(fig_env("monte_carlo", f"Tuning error after calibration across {len(w1)} simulated builds."))
    T.append(table("lrrrr", ["Resistors", "Cal. failures", "Median worst key", "95th pct", "Max"], [
        ["1 \\% (specified)", f"{mc1['calibration_failures']}/{mc1['trials']}", f"{mc1['worst_key_cents_median']} ct",
         f"\\textbf{{{mc1['worst_key_cents_p95']} ct}}", f"{mc1['worst_key_cents_max']} ct"],
        ["0.1 \\% (upgrade)", f"{mc01['calibration_failures']}/{mc01['trials']}", f"{mc01['worst_key_cents_median']} ct",
         f"{mc01['worst_key_cents_p95']} ct", f"{mc01['worst_key_cents_max']} ct"]],
        caption="Worst-key tuning error per build (1 cent = 1/100 semitone; about 5--10 cents is the "
                "threshold of audibility)."))

    T.append(r"\section{Schematic and electrical rules}" + rf"""
The schematic is generated from \texttt{{circuit.py}} and checked by round-trip: KiCad exports its netlist,
which is compared with the design source. \textbf{{Result:}} {tex(st['netlist']['detail'])}.

KiCad~7 has no command-line ERC, so a static rule check runs on the netlist using the official KiCad symbol
pin types. It covers {erc['nets']} nets and {erc['pins']} pins, and checks for: multiple drivers on one net,
power inputs without a source, floating inputs and single-pin nets. \textbf{{Result: {len(erc['issues'])}
issues}} {status(erc['ok'])}. Waived, intentional cases:
\begin{{itemize}}{''.join(f'{chr(92)}item {tex(w)}' for w in erc['waived'])}\end{{itemize}}
\begin{{figure}}[H]\centering\includegraphics[width=\textwidth]{{figures/schematic}}
\caption{{Generated schematic (vector; the full-size sheet is in Appendix~\ref{{app:sch}}).}}\end{{figure}}
""")

    T.append(r"\section{Power, ratings and dissipation}" + "Datasheet-typical values, not measurements.\n")
    T.append(fig_env("power", "Idle current budget."))
    T.append(table("p{5.2cm}p{4.6cm}p{3.4cm}l", ["Item", "Value", "Limit / note", "Status"],
                   [[tex(a), tex(b), tex(c_), status(ok)] for a, b, c_, ok in bud["checks"]],
                   caption="Power and dissipation checks.", size=r"\footnotesize"))
    caps = bud["caps"]
    half = (len(caps) + 1) // 2
    rows = []
    for i in range(half):
        r = [tex(caps[i][0]), tex(caps[i][1]), f"{caps[i][2]:g} V", f"{caps[i][3]:g} V", status(caps[i][4])]
        if i + half < len(caps):
            cc = caps[i + half]
            r += [tex(cc[0]), tex(cc[1]), f"{cc[2]:g} V", f"{cc[3]:g} V", status(cc[4])]
        else:
            r += [""] * 5
        rows.append(r)
    T.append(table("lllll|lllll", ["Cap", "Value", "Rated", "Worst", ""] * 2, rows,
                   caption=r"Capacitor voltage ratings ($\geq$1.25$\times$ the worst-case net voltage; 12\,V assumed "
                           r"on the 9\,V side).", size=r"\footnotesize"))
    T.append(r"\noindent\textbf{Note:} the LM386N-1 operating range is 4--12\,V, so use a \emph{regulated} 9\,V "
             r"adapter." + "\n")

    T.append(r"\section{PCB}" + rf"""
136\,$\times$\,98\,mm, two layers, 1.6\,mm FR-4, ENIG finish (the keys are exposed copper). Routed with
Freerouting; the ground net is carried by copper pours on both layers, with the pour kept out of the
keyboard area. Statistics: {c['footprints']} footprints, {c['tracks']} track segments, {c['vias']} vias,
{c['pours_filled']}/{c['pours']} pours filled.
\begin{{figure}}[H]\centering
\includegraphics[width=\textwidth, trim={trim}, clip]{{figures/pcb_front}}
\caption{{Front copper and silkscreen. The 20 piano-style keys are exposed ENIG pads; the ladder resistors
sit in a row directly above the key vias.}}\end{{figure}}
\begin{{figure}}[H]\centering
\begin{{subfigure}}{{0.49\textwidth}}\includegraphics[width=\linewidth, trim={trim}, clip]{{figures/pcb_back}}
\caption{{Back copper}}\end{{subfigure}}\hfill
\begin{{subfigure}}{{0.49\textwidth}}\includegraphics[width=\linewidth, trim={trim}, clip]{{figures/pcb_copper}}
\caption{{Both copper layers}}\end{{subfigure}}
\caption{{PCB layers.}}\end{{figure}}
""")
    rows = [["DRC errors (incl. unconnected items)", str(drc_err), status(drc_err == 0)],
            ["DRC warnings (cosmetic)", tex(", ".join(f"{k} {v}" for k, v in drc_warn.items()) or "none"), "--"],
            [r"Schematic $\leftrightarrow$ PCB pad nets", f"{len(pcb['parity'])} mismatches / {pcb['parity_pins']} pins",
             status(not pcb["parity"])],
            ["Min. track width", tex(", ".join(f"{k} {v:.2f} mm" for k, v in sorted(pcb['widths'].items()))), "--"]]
    for name, best in pcb["decoupling"]:
        lvl = r"\pass" if best[1] < verify_all.DECOUPLE_OK_MM else r"\warn"
        rows.append([f"Decoupling {tex(name)}", f"{best[0]} ({tex(best[2])}) at {best[1]:.1f} mm", lvl])
    T.append(table("p{6cm}p{6.2cm}l", ["Check", "Result", "Status"], rows, caption="PCB verification.",
                   size=r"\footnotesize"))
    if pcb["findings"]:
        T.append(r"\noindent\textbf{Finding:} " + tex(pcb["findings"][0]) +
                 " Severity is low: U5 only runs the vibrato LFO, from the LDO-filtered rail.\n")

    T.append(r"\section{Enclosures}" + rf"""
Both enclosures use the PCB as the top face, held at its four M3 holes. The battery and speaker sit
underneath, and all jacks and switches stand above the enclosure edge, so no cut-outs are needed. A geometric
fit check confirms the battery, speaker, bosses and pillars clear the back-side parts and THT leads by at
least 1\,mm. \textbf{{Result:}} {tex(fit['detail'])}.
\begin{{figure}}[H]\centering\includegraphics[width=\textwidth]{{renders/enclosures_overview}}
\caption{{3D-printed tray with stylus (left) and laser-cut acrylic stack (right), modelled in Blender with
the textured PCB and components.}}\end{{figure}}
\begin{{figure}}[H]\centering
\begin{{subfigure}}{{0.49\textwidth}}\includegraphics[width=\linewidth]{{renders/printed_closeup}}
\caption{{Printed tray: PETG, 141.8$\times$103.8$\times$25.6\,mm, $\approx$62\,cm$^3$}}\end{{subfigure}}\hfill
\begin{{subfigure}}{{0.49\textwidth}}\includegraphics[width=\linewidth]{{renders/acrylic_closeup}}
\caption{{Acrylic: 1 base + 8 rings, 3\,mm, 151$\times$113\,mm}}\end{{subfigure}}
\caption{{Enclosure variants.}}\end{{figure}}
""")

    T.append(r"\section{Verification summary}" + table(
        "clp{5.2cm}l", ["\\#", "Check", "Method", "Result"], [
            ["1", "Circuit behaviour", "ngspice, behavioural models", status(st["sims"]["ok"])],
            ["2", "Tuning accuracy", f"{mc1['trials']}-build tolerance analysis + calibration", status(st["sims"]["ok"])],
            ["3", "Schematic vs source", "netlist round-trip", status(st["netlist"]["ok"])],
            ["4", "Electrical rules", "static ERC on symbol pin types", status(erc["ok"])],
            ["5", "Power and ratings", "hand calculations", status(bud["ok"])],
            ["6", "PCB", "DRC, parity, decoupling", status(pcb["ok"])],
            ["7", "Mechanical fit", "geometry check", status(fit["ok"])]], caption="Automated verification."))
    T.append(r"""
\subsection*{Not yet verified}
\begin{itemize}
\item Jack and switch pin behaviour (SJ1-3535NG speaker mute, PJ-102AH battery break, JS202011 slider sense),
assumed from KiCad symbols. Check against the datasheets and on a breadboard.
\item Real IC behaviour with vendor SPICE models (TLC555 output resistance, LM386 stability and hum).
\item KiCad GUI ERC (Inspect $\rightarrow$ Electrical Rules Checker).
\item Physical footprint fit: print the PCB at 1:1 and test-fit the pots, switches, jacks and trimmers.
\item Stylus-lift clicks, ESD, finger hum, and 5\,V rail ripple at full volume, on a prototype.
\end{itemize}
""")

    bom = list(csv.reader(open(ROOT / "bom" / "bom.csv")))
    hdr, body = bom[0], bom[1:]
    rows = [[tex(r[0]), tex(r[1] if len(r[1]) < 48 else r[1][:45] + "…"), tex(r[2]), tex(r[5]),
             tex(r[6] if len(r[6]) < 46 else r[6][:43] + "…"), tex(r[9])] for r in body]
    total = sum(float(r[9]) for r in body)
    T.append(r"\appendix\section{Bill of materials}" + table(
        "rp{3.6cm}lp{2.2cm}p{4.6cm}r", ["Qty", "Refs", "Value", "Mfr", "MPN / description", "USD"], rows,
        caption=f"BOM (estimated prices, total \\${total:.2f}). Full detail in \\texttt{{bom/bom.csv}}.",
        size=r"\scriptsize", long=True))
    T.append(r"""\section{Schematic}\label{app:sch}
The complete generated schematic follows on the next page (landscape, vector: zoom in for detail). The source
file is \texttt{hardware/kicad/stylosynth.kicad\_sch}.
\newpage\newgeometry{margin=8mm}\thispagestyle{empty}
\special{pdf:put @thispage << /Rotate 90 >>}
\begin{center}\includegraphics[angle=90, height=0.96\textheight, width=\textwidth, keepaspectratio]{figures/schematic}
\end{center}\restoregeometry""")
    T.append(r"\end{document}")
    return "\n".join(T)


def main():
    st = collect()
    lad = st["sims"]["ladder"]
    sims = st["sims"]["results"]
    FIG.mkdir(parents=True, exist_ok=True)
    print("figures ...", flush=True)
    ng = NgSpice()
    fig_note_map(lad)
    fig_ladder(lad, sims)
    fig_555(ng, lad)
    vstat = fig_lfo(ng, lad)
    fig_audio(ng)
    fig_lfo_rate(sims)
    fig_power(st["budgets"])
    print("monte carlo ...", flush=True)
    errs1 = monte_carlo_per_key(lad)
    errs01 = monte_carlo_per_key(lad, r_tol=0.001)
    fig_monte_carlo(errs1, errs01)
    with tempfile.TemporaryDirectory() as td:
        trim = board_plots(td)
    shutil.copy(ROOT / "hardware" / "fab" / "stylosynth-schematic.pdf", FIG / "schematic.pdf")
    renders = HERE / "renders"
    renders.mkdir(exist_ok=True)
    for p in (ROOT / "docs" / "renders").glob("*.png"):
        shutil.copy(p, renders / p.name)

    rev = verify_all.run(["git", "rev-parse", "--short", "HEAD"])[1]
    (HERE / "report.tex").write_text(build_tex(st, errs1, errs01, trim, rev, vstat))
    print("compiling ...", flush=True)
    p = subprocess.run([str(TECTONIC), "-X", "compile", "report.tex"], cwd=HERE, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout[-3000:], p.stderr[-3000:])
        return 1
    (HERE / "report.pdf").replace(HERE / PDF_NAME)
    print(f"wrote {(HERE / PDF_NAME).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
