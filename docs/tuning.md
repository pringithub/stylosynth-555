# StyloSynth-555: tuning guide

Each key has its own 25-turn trimmer. The ladder is a chain, so a key's pitch depends on
**every key to its right**. Always tune **from key 20 (rightmost, highest E) leftwards to key 1 (A)**.
Once a key is tuned, adjusting keys to its left does not change it.

## Octave switches
The CD4040 divides the oscillator by exactly 2, 4, 8 or 16, so the octaves are always perfect.
You only need to tune at one setting.

| OCT-1 | OCT-2 | Divider | Range (key 1 to key 20) |
|---|---|---|---|
| off | off | ÷2 | A4 – E6 |
| **on** | off | ÷4 | **A3 – E5** (recommended for tuning) |
| off | on | ÷8 | A2 – E4 |
| on | on | ÷16 | A1 – E3 |

Which slider direction counts as "on" depends on the switch. Check by ear once and mark it.

## Procedure
1. Vibrato **off**, tone **bright**, volume medium. Let the board warm up for a minute.
2. Set OCT-1 on and OCT-2 off (A3–E5). Open a chromatic tuner app next to the speaker, or plug
   headphones into a tuner.
3. **Key 20 (E5): adjust RV101 (5k master trimmer)** until the tuner reads E. This sets the pitch of
   the whole instrument.
4. Key 19 (D#5): RV102. Key 18 (D5): RV103. Continue leftwards: **key *k* is trimmed by
   RV(121 − *k*)**. The trimmer sits directly above its key.
5. Finish at key 1 (A3) with RV120.
6. Recheck a few keys. If key 20 drifted (temperature), retouch RV101. That shifts every key by the
   same ratio, so the relative tuning stays correct.

Turning a trimmer clockwise usually *raises* its resistance and *lowers* the pitch. If a key goes the
wrong way, turn the other way. There is about ±12 % of range, so every key reaches its note
even with a 5 % timing capacitor.

## Vibrato
- **RV2 (rate trimmer):** about 4–9.5 Hz; 5–6 Hz sounds classic.
- **DEPTH pot (RV3):** 0 to about ±45 cents. The VIB switch turns it on and off without clicks.

## Reference values
The design values for every segment (target Hz, fixed resistor, trimmer, expected wiper position)
are in [hardware/design/ladder.csv](../hardware/design/ladder.csv). With the right note, most trimmers
sit near mid-travel (0.5–0.67).
