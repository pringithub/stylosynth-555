#!/usr/bin/env python3
"""Generate the 20-key exposed-copper keypad footprint (StyloSynth:KEYPAD_20).

Each key is a mask-opened roundrect SMD pad (ENIG finish) plus a plated through-hole with
the same pad number that overlaps the key, so the back-side ladder trace always lands on it.
Origin = top centre of the keyboard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sexpr import Sym as S, dumps  # noqa: E402

HW = Path(__file__).resolve().parents[1]
OUT = HW / "kicad" / "lib" / "StyloSynth.pretty" / "KEYPAD_20.kicad_mod"

N_KEYS = 20
PITCH = 8.0
KEY_W = 7.0
NATURAL_L = 40.0
SHARP_L = 26.0
VIA_Y = 2.5
NOTES = ["A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#"]


def key_x(i):
    return round((i - (N_KEYS + 1) / 2) * PITCH, 4)


def text(kind, value, x, y, layer, size=1.0, thick=0.15):
    return [S("fp_text"), S(kind), value, [S("at"), x, y], [S("layer"), layer],
            [S("effects"), [S("font"), [S("size"), size, size], [S("thickness"), thick]]]]


def rect(x0, y0, x1, y1, layer, width):
    return [S("fp_rect"), [S("start"), x0, y0], [S("end"), x1, y1],
            [S("stroke"), [S("width"), width], [S("type"), S("solid")]], [S("fill"), S("none")], [S("layer"), layer]]


def main():
    half = N_KEYS * PITCH / 2
    fp = [S("footprint"), "KEYPAD_20", [S("version"), 20221018], [S("generator"), S("pcbnew")],
          [S("layer"), "F.Cu"],
          [S("descr"), "StyloSynth 20-key stylus keypad, 8 mm pitch, exposed ENIG copper"],
          [S("tags"), "stylophone keypad stylus"],
          [S("attr"), S("through_hole"), S("exclude_from_pos_files"), S("exclude_from_bom")],
          text("reference", "K1", -half + 4, -2.0, "F.Fab"),
          text("value", "KEYPAD", 0, NATURAL_L + 6.5, "F.Fab"),
          rect(-half - 1.5, -1.0, half + 1.5, NATURAL_L + 5.0, "F.SilkS", 0.2),
          rect(-half - 2.0, -1.5, half + 2.0, NATURAL_L + 5.5, "F.CrtYd", 0.05)]
    for i in range(1, N_KEYS + 1):
        x = key_x(i)
        note = NOTES[(i - 1) % 12]
        sharp = "#" in note
        length = SHARP_L if sharp else NATURAL_L
        fp.append([S("pad"), str(i), S("smd"), S("roundrect"), [S("at"), x, length / 2],
                   [S("size"), KEY_W, length], [S("layers"), "F.Cu", "F.Mask"], [S("roundrect_rratio"), 0.15]])
        fp.append([S("pad"), str(i), S("thru_hole"), S("circle"), [S("at"), x, VIA_Y],
                   [S("size"), 1.6, 1.6], [S("drill"), 0.8], [S("layers"), "*.Cu", "*.Mask"]])
        label_y = SHARP_L + 2.0 if sharp else NATURAL_L + 2.5
        fp.append(text("user", note, x, label_y, "F.SilkS", 1.2, 0.2))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dumps(fp) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
