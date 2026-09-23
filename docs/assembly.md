# StyloSynth-555: assembly guide

All parts are through-hole. Parts are placed from the front (the key side) and soldered on the
back, **except J2 (battery) and J5 (speaker)**. Those two headers go on the **back side** and are
soldered from the front, so their cables stay inside the enclosure.

## Before you start
- Board: 2-layer, **ENIG finish** (required, because the keys are bare copper).
- Tools: fine soldering iron (about 330 °C), flush cutters, multimeter, and a tuner app or tuner.
- Check the parts against [bom/bom.md](../bom/bom.md).

## Solder order (lowest parts first)
1. **Resistors, horizontal:** R1–R14. The ladder resistors R101–R120 (1 % E96 values, check each
   with a meter; they set the key pitches) stand **vertically**: body over the round pad, lead bent
   back to the second pad.
2. **Diode D1** (1N5819): the band goes to the "K" end marked on the silkscreen.
3. **Ceramic caps:** C2, C5, C6, C8, C9, C14, C15, C17.
4. **IC sockets:** U2, U4, U5 (DIP-8) and U3 (DIP-16). Match the notch to the silkscreen.
   Do not insert the ICs yet.
5. **Film caps:** C7 (22 nF polypropylene: the tuning reference, use the good one), C10, C11, C18.
6. **U1** LP2950-5.0 (TO-92): the flat face matches the silkscreen.
7. **Trimmers:** RV4 TUNE (2k), RV5 SPAN (1k), RV2 RATE (100k).
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

## Enclosure
Both versions leave the PCB exposed as the top face. It is held by the 4 M3 holes, and the 9 V battery
and speaker sit underneath. The jacks and switches stay above the enclosure edge, so no cut-outs are
needed. Files are in `enclosure/out/`. To regenerate them, run `enclosure/gen_geometry.py`, then
`enclosure/blender_build.py` inside Blender. The model is in `stylosynth_enclosures.blend`, and the renders are in
[docs/renders](renders/).

### A) 3D-printed tray (`print/tray.stl`, 141.8 × 103.8 × 25.6 mm, about 62 cm³)
- **Print settings:** PETG or PLA, 0.2 mm layers, 3 walls, 15 % infill. Print floor down; no supports are needed.
- Press **4 × M3 × 5.7 heat-set inserts** into the corner bosses (4.0 mm holes).
- **Speaker:** a 40 mm, 8 Ω speaker drops into the printed ring over the grille. Fix it with a few dots of hot glue.
- **Battery:** the 9 V battery sits between the corner ribs. Its snap lead goes to J2 (back side).
- Plug the speaker into J5, lay the PCB in (it sits flush with the wall top), and fit **4 × M3 × 6** screws.
- **Feet:** stick 4 × 10 mm rubber bumpers in the recesses.
- **Stylus** (`print/stylus_body.stl`): print it standing up, 0.12 mm layers.
  - Feed the cable through the 4 mm channel and solder it to a 4 mm banana plug.
  - Press the plug into the tip socket.
  - Fit a 3.5 mm mono plug on the other end.

### B) Laser-cut acrylic stack (`acrylic/*.dxf`, 3 mm clear cast acrylic, units mm, layer `CUT`)
| File | Qty | Purpose |
|---|---|---|
| `bottom_plate_x1.dxf` | 1 | base: speaker grille, battery strap slots, standoff and corner-bolt holes |
| `ring_x8.dxf` | 8 | side walls, stacked 24 mm high |
1. Screw **4 × M3 × 25 brass standoffs** to the bottom plate from underneath (M3 × 6).
2. Glue the speaker over the grille, and strap the battery with velcro through the slots.
3. Stack the 8 rings and clamp everything with **4 × M3 × 30** corner bolts and nuts.
4. Place the PCB on the standoffs (it floats 1 mm above the rings) and fit 4 × M3 × 6 screws.

A fit check in `gen_geometry.py` confirms that the battery, speaker, bosses and pillars clear the back-side
parts and the THT leads, with at least 1 mm to spare, in both versions.

Next step: [tuning.md](tuning.md).
