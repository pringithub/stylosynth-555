# StyloSynth-555: electrical verification report

Generated 2026-10-05 15:27 by `hardware/scripts/verify_all.py` against commit `83e091d`. Re-run the script after any design change.

## Summary

| # | Check | Method | Result |
|---|---|---|---|
| 1 | Circuit behaviour | ngspice transient/AC with behavioural models | ✅ PASS |
| 2 | Tuning accuracy | Monte Carlo, 2000 builds, with two-point calibration | ✅ PASS |
| 3 | Schematic matches design source | KiCad netlist export vs `circuit.py` | ✅ PASS |
| 4 | Electrical rules (static ERC) | KiCad symbol pin types, all 59 nets / 210 pins | ✅ PASS |
| 5 | Power, ratings and dissipation | Hand calculations, datasheet typicals | ✅ PASS |
| 6 | PCB DRC + schematic parity | pcbnew DRC, pad-net comparison, decoupling distance | ✅ PASS |
| 7 | Mechanical fit in enclosures | Geometry check of internal parts vs PCB underside | ✅ PASS |

**Verdict:** the design is consistent and meets its targets *in simulation and static analysis*. It has **not** been validated on hardware. See [What is not verified](#what-is-not-verified) before ordering more than a prototype batch.

## Findings (fix in the next revision)

- ⚠️ U5 pin 8 (+5V): nearest decoupling cap C17 is 17.0 mm away (target < 12 mm). Move C17 next to the supply pin in the next revision.

Severity is low: U5 only runs the 4–10 Hz vibrato LFO, and it is powered from the LDO-filtered 5 V rail with C4/C5 nearby. Still, it is not good practice and should be corrected.

> ⚠️ **Working-copy PCB differs from the verified board.** `hardware/kicad/stylosynth.kicad_pcb` on disk has 0 tracks / 0 vias / 0 GND pours, while the committed board has 617 / 3 / 2. The routing appears to have been removed. The fab package in `hardware/fab/` matches the **committed** board. Restore it with `git checkout hardware/kicad/stylosynth.kicad_pcb` or re-run `build_pcb.py finish`.

## 1. Circuit simulation

Behavioural models: a CMOS 555 as a Schmitt switch with 100 Ω output resistance, and an LM358 as a saturating gain stage. Source: `hardware/sim/run_sims.py`, results in `hardware/sim/results.json`.

| Block | Target | Result | Status |
|---|---|---|---|
| Key ladder, all 20 keys, ngspice vs analytic model | spread < 2 cents | 0.54 cents spread | ✅ PASS |
| Uncalibrated pitch error (nominal parts) | absorbed by TUNE/SPAN | worst 0.561 % | info |
| Vibrato LFO rate over RATE trimmer range | covers 5–7 Hz | 3.88–9.57 Hz | ✅ PASS |
| Vibrato depth at full DEPTH | 25–80 cents | ±45.6 cents | ✅ PASS |
| CV node DC with LFO running | ≈ 3.2955 V | 3.2956 V | ✅ PASS |
| LM386 drive at full volume | 2.0–3.8 V pk (no hard clipping) | 3.35 V pk | ✅ PASS |
| Audio high-pass corner (bright) | < 40 Hz | 10.4 Hz | ✅ |
| SOFT tone low-pass corner | ≈ 0.5–1 kHz | 629.5 Hz | ✅ |

## 2. Tuning accuracy (tolerance analysis)

The analytic oscillator model is validated against ngspice in section 1. The analysis applies random part tolerances, emulates the TUNE→key 20 / SPAN→key 1 calibration, then measures every key. Varied: R ±1 % (or ±0.1 %), C_T ±2.5 %, 555 output plus stylus resistance 100–700 Ω, and the 555 internal divider 20–300 kΩ.

| Resistors | Calibration failures | Worst key, median | Worst key, 95th pct | Worst key, max |
|---|---|---|---|---|
| 1 % (as specified) | 0 / 2000 | 2.34 ct | **3.59 ct** | 5.01 ct |
| 0.1 % (optional upgrade) | 0 / 2000 | 1.62 ct | 1.75 ct | 1.84 ct |

Octaves are exact by construction: the CD4040 binary divider gives ratios of exactly 2.

## 3. Schematic vs design source

`verify_netlist.py`: PASS: 59 nets and 81 components match circuit.py. The KiCad schematic is regenerated from `circuit.py`, then exported with `kicad-cli sch export netlist`. Every net and every component's value and footprint are compared.

## 4. Static electrical rules check

KiCad 7 has no command-line ERC, so these rules are checked on the design netlist using the official KiCad symbol pin types:
- No net has more than one output or power-output pin (outputs would fight each other).
- Every power-input pin's net has a power source or a PWR_FLAG.
- No input pin is left floating.
- No net has only one connection.

Result: **0 issues**.

Waived (intentional):
- U2 pin 7 unconnected - TLC555 DIS is an open-drain output (KiCad types it as input); unused in this topology
- U4 pin 1 unconnected - LM386 GAIN pins left open = gain 20 (datasheet default)
- U4 pin 8 unconnected - LM386 GAIN pins left open = gain 20 (datasheet default)

## 5. Power, ratings and dissipation

These are datasheet-typical values, not measurements.

| Item | Value | Limit / note | Status |
|---|---|---|---|
| Idle supply current | 7.5 mA | ≈ 73 h idle on a 550 mAh alkaline 9 V | ✅ PASS |
| LM386 output at full volume (sim) | 3.35 V pk → 701 mW sine-equivalent into 8 Ω | use a ≥ 1 W speaker | ✅ PASS |
| LM386N-1 worst-case dissipation | 549 mW | DIP-8 rating 1.25 W at 25 °C | ✅ PASS |
| LP2950 dissipation | 10.7 mW at 3 mA | TO-92 rating ≈ 600 mW | ✅ PASS |
| R9 (220 Ω) with shorted headphone plug | 51 mW | 0.25 W rating | ✅ PASS |
| R1 LED resistor | 9.7 mW | 0.25 W rating | ✅ PASS |
| D1 1N5819 current / reverse voltage | < 0.3 A / ≤ 12 V | 1 A / 40 V rating | ✅ PASS |

Idle current breakdown (mA): Power LED (R1 4k7) 1.44, LM386 quiescent (typ) 4.00, LM358 quiescent at 5 V (typ) 0.70, TLC555 at 5 V (typ) 0.17, CV divider R4/R5/RV5 1.14, LFO hysteresis network 0.03, LP2950 ground current (typ) 0.07

Capacitor voltage ratings (worst-case net voltage, 12 V assumed on the 9 V side for an unregulated adapter, 1.25× margin required):

| Cap | Value | Rated | Worst case | Status |
|---|---|---|---|---|
| C1 | 220u | 16 V | 12 V | ✅ PASS |
| C2 | 100n | 50 V | 12 V | ✅ PASS |
| C3 | 100u | 16 V | 12 V | ✅ PASS |
| C4 | 10u | 25 V | 5 V | ✅ PASS |
| C5 | 100n | 50 V | 5 V | ✅ PASS |
| C6 | 100n | 50 V | 5 V | ✅ PASS |
| C7 | 22n | 100 V | 5 V | ✅ PASS |
| C8 | 10n | 50 V | 5 V | ✅ PASS |
| C9 | 100n | 50 V | 5 V | ✅ PASS |
| C10 | 47n | 63 V | 5 V | ✅ PASS |
| C11 | 100n | 63 V | 5 V | ✅ PASS |
| C12 | 10u | 25 V | 12 V | ✅ PASS |
| C13 | 100u | 16 V | 12 V | ✅ PASS |
| C14 | 100n | 50 V | 12 V | ✅ PASS |
| C15 | 47n | 50 V | 5 V | ✅ PASS |
| C16 | 220u | 16 V | 12 V | ✅ PASS |
| C17 | 100n | 50 V | 5 V | ✅ PASS |
| C18 | 1u | 63 V | 5 V | ✅ PASS |
| C19 | 22u | 25 V | 5 V | ✅ PASS |
| C20 | 47u | 25 V | 5 V | ✅ PASS |

⚠️ The **LM386N-1 operating range is 4–12 V**. Use a *regulated* 9 V adapter; unregulated wall adapters can exceed 12 V when lightly loaded.

## 6. PCB

Board verified: committed `stylosynth.kicad_pcb`, 81 footprints, 617 track segments, 3 vias, 2/2 GND pours filled.

- **DRC errors:** none (including 0 unconnected items)
- DRC warnings (cosmetic silkscreen / dangling stubs): {'silk_overlap': 23, 'silk_over_copper': 5, 'silk_edge_clearance': 2, 'track_dangling': 2}
- **Schematic ↔ PCB parity:** 0 mismatches across 210 connected pins
- Minimum track width per net class: Default 0.25 mm, Ground 0.50 mm, Power 0.50 mm
- Fab package: 14 files in `hardware/fab/gerbers`, F.Cu has 13218 draw commands (routing present)

| IC supply pin | Nearest decoupling cap | Distance | Status |
|---|---|---|---|
| U2 pin 8 (+5V) | C6 (100n) | 6.0 mm | ✅ PASS |
| U3 pin 16 (+5V) | C9 (100n) | 6.8 mm | ✅ PASS |
| U4 pin 6 (+9V) | C13 (100u) | 5.6 mm | ✅ PASS |
| U5 pin 8 (+5V) | C17 (100n) | 17.0 mm | ⚠️ WARN |
| U1 pin 1 (+5V) | C4 (10u) | 7.6 mm | ✅ PASS |

## 7. Mechanical fit

`enclosure/gen_geometry.py`: fit check: PASS (battery, speaker, bosses, pillars clear of back-side parts and leads)

## What is not verified

These are the remaining risks, roughly in order of how likely they are to bite:

| Risk | Why it is open | How to close it |
|---|---|---|
| Jack/switch pin semantics | Assumed from KiCad symbols: SJ1-3535NG tip/ring normals for speaker mute, PJ-102AH pin 3 battery break, JS202011 slider direction | Check against the datasheets, and test on a breadboard or the first board |
| Real IC behaviour | Behavioural models only: TLC555 output resistance, LM358 swing, LM386 stability and hum are not simulated with vendor models | Re-run with TI SPICE models; breadboard the oscillator and amp |
| KiCad GUI ERC | Not available in the KiCad 7 CLI; replaced by section 4 | Open the schematic in KiCad and run Inspect → ERC |
| Footprint vs physical part | Library footprints assumed to match the purchased parts (pots, switches, jacks, 3296W) | Print the PCB at 1:1 and test-fit the real parts |
| Stylus-lift click, ESD, finger hum | Not modelled | Listen and probe on the prototype |
| Supply sag at full volume | Battery ESR not in the simulation | Measure 5 V rail ripple on the prototype at full volume |

