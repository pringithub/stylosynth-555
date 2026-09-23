# StyloSynth-555: tuning guide

The key ladder uses fixed 1 % resistors, so there are no per-key trimmers. Two trimmers calibrate
the whole keyboard at once:

| Trimmer | Location | What it does | Tune on |
|---|---|---|---|
| **RV4 TUNE** | right of the keyboard, "TUNE (key 20)" | adds an offset in series with the whole ladder | key 20 (top E) |
| **RV5 SPAN** | oscillator block, "SPAN (key 1)" | scales every note by the same ratio (555 CV divider) | key 1 (bottom A) |

Monte Carlo analysis with 1 % resistors and a 2.5 % timing capacitor (2000 builds) puts the worst key
within **±3.6 cents in 95 % of builds (5 cents max)** after this two-point calibration
(see `monte_carlo_1pct` in [ladder.json](../hardware/design/ladder.json)). Most listeners can't
hear that. With 0.1 % resistors it drops below 2 cents.

## Octave switches
The CD4040 divides the oscillator by exactly 2, 4, 8 or 16, so octaves are always perfect.
Calibrate at one setting only.

| OCT-1 | OCT-2 | Divider | Range (key 1 to key 20) |
|---|---|---|---|
| off | off | ÷2 | A4 – E6 |
| **on** | off | ÷4 | **A3 – E5** (recommended for tuning) |
| off | on | ÷8 | A2 – E4 |
| on | on | ÷16 | A1 – E3 |

Which slider direction counts as "on" depends on the switch. Check by ear once and mark it.

## Procedure (2–3 passes)
1. Vibrato **off**, tone **bright**, medium volume. Let the board warm up for a minute.
2. Set OCT-1 on and OCT-2 off, and open a chromatic tuner app next to the speaker.
3. Play **key 20 (E5)**. Adjust **TUNE** until the tuner shows E.
4. Play **key 1 (A3)**. Adjust **SPAN** until the tuner shows A.
5. Go back to key 20 and repeat steps 3–4 until both are in tune without further adjustment.
   The two controls interact a little; it usually converges in 2–3 passes.
6. Spot-check a few keys in the middle. They should all be within a few cents.

Turning **SPAN** changes every key by the same ratio. **TUNE** has the most effect on the top keys.

## Vibrato
- **RV2 (rate trimmer):** about 4–9.5 Hz; 5–6 Hz sounds classic.
- **DEPTH pot (RV3):** 0 to about ±45 cents. The VIB switch turns it on and off without clicks.

## Reference values
Ladder resistor values and per-key design frequencies are in
[hardware/design/ladder.csv](../hardware/design/ladder.csv).
