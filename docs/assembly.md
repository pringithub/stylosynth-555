# StyloSynth-555: assembly guide

All parts are through-hole. Parts are placed from the front (the key side) and soldered on the
back, **except J2 (battery) and J5 (speaker)**. Those two headers go on the **back side** and are
soldered from the front, so their cables stay inside the enclosure.

## Before you start
- Board: 2-layer, **ENIG finish** (required, because the keys are bare copper).
- Tools: fine soldering iron (about 330 °C), flush cutters, multimeter, and a tuner app or tuner.
- Check the parts against [bom/bom.md](../bom/bom.md).

## Solder order (lowest parts first)
1. **Resistors, horizontal:** R1–R14. The ladder resistors R101–R120 stand **vertically**
   (body over the round pad, lead bent back to the second pad).
2. **Diode D1** (1N5819): the band goes to the "K" end marked on the silkscreen.
3. **Ceramic caps:** C2, C5, C6, C8, C9, C14, C15, C17.
4. **IC sockets:** U2, U4, U5 (DIP-8) and U3 (DIP-16). Match the notch to the silkscreen.
   Do not insert the ICs yet.
5. **Film caps:** C7 (22 nF polypropylene: the tuning reference, use the good one), C10, C11, C18.
6. **U1** LP2950-5.0 (TO-92): the flat face matches the silkscreen.
7. **Trimmers:** RV101 (5k), RV102–RV120 (1k), RV2 (100k). The adjust screws should all face the
   same way for easy tuning.
8. **Electrolytics:** C1, C3, C4, C12, C13, C16, C19, C20. **Polarity:** the long lead goes in the "+"
   pad (the square pad).
9. **LED D2:** long lead (anode) to the round "A" pad, flat side (cathode) to the square pad.
10. **Switches** SW1–SW5, **pots** RV1 (A10k volume), RV3 (B10k depth), **jacks** J1, J3, J4.
11. **Back side:** J2 and J5 (JST XH), soldered from the front.

## Smoke test (ICs still out)
| Check | Expected |
|---|---|
| Battery connected, power off: current | 0 mA |
| Power on: across C1 (+9V) | battery voltage minus about 0.3 V (Schottky drop) |
| Across C4 (+5V) | 4.95–5.05 V |
| Supply current, no ICs | < 3 mA (LED plus regulator) |
| Plug in a 9 V centre-negative adapter | battery disconnects (J1 switch); +9V still present |

## Insert the ICs (power off)
U2 **TLC555** (CMOS; do *not* use an NE555, whose output does not swing rail-to-rail), U3 **CD4040**,
U4 **LM386**, U5 **LM358**. Check the pin-1 notch. The CD4040 and TLC555 are CMOS, so handle them with ESD care.

## Power-on checks (ICs in)
| Point | Expected |
|---|---|
| Idle supply current | about 8–12 mA |
| U2 pin 5 (CV) | about 3.33 V |
| U4 pin 5 (amp output, DC) | about half of +9V |
| U5 pin 1 (LFO square) | toggling 0 ↔ about 3.5 V at 4–9 Hz |
| Stylus on any key | tone from the speaker; plugging in headphones mutes the speaker |

Next step: [tuning.md](tuning.md).
