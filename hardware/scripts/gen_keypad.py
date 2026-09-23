#!/usr/bin/env python3
"""Generate the 20-key piano-layout keypad footprint (StyloSynth:KEYPAD_20).

Stylophone-style compact keyboard: 12 naturals side by side, notched at the top where the 8
sharps sit between them. Keys are mask-opened copper (order ENIG). Each key also carries a
plated through-hole with the same pad number at its top edge, where the ladder trace lands.
Pad numbers are chromatic: 1 = A (lowest) ... 20 = E (highest). Origin = top-left of the keyboard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sexpr import Sym as S, dumps  # noqa: E402

HW = Path(__file__).resolve().parents[1]
OUT = HW / "kicad" / "lib" / "StyloSynth.pretty" / "KEYPAD_20.kicad_mod"

CHROMATIC = ["A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#",
             "A", "A#", "B", "C", "C#", "D", "D#", "E"]
PITCH = 8.0          # natural key pitch
GAP = 0.8            # copper gap between keys
SHARP_W = 4.6
SHARP_L = 22.0
NATURAL_L = 36.0
VIA_Y = 1.6
VIA_PAD, VIA_DRILL = 1.4, 0.6


def layout():
    """[(pad_no, note, kind, geometry)] with naturals as polygons and sharps as rects."""
    nat_index, keys = -1, []
    for n, note in enumerate(CHROMATIC, start=1):
        if "#" in note:
            keys.append((n, note, "sharp", (nat_index + 1) * PITCH))
        else:
            nat_index += 1
            keys.append((n, note, "natural", nat_index))
    sharp_bounds = {k[3] for k in keys if k[2] == "sharp"}
    out = []
    for n, note, kind, g in keys:
        if kind == "sharp":
            out.append((n, note, kind, {"cx": g, "via_x": g}))
            continue
        left, right = g * PITCH, (g + 1) * PITCH
        xl, xr = left + GAP / 2, right - GAP / 2
        ul = left + SHARP_W / 2 + GAP if left in sharp_bounds else xl
        ur = right - SHARP_W / 2 - GAP if right in sharp_bounds else xr
        y_step = SHARP_L + GAP
        poly = [(ul, 0), (ur, 0), (ur, y_step), (xr, y_step), (xr, NATURAL_L), (xl, NATURAL_L), (xl, y_step),
                (ul, y_step)]
        out.append((n, note, kind, {"poly": poly, "via_x": (ul + ur) / 2, "cx": (xl + xr) / 2}))
    return out, (nat_index + 1) * PITCH


def text(kind, value, x, y, layer, size=1.0, thick=0.15):
    return [S("fp_text"), S(kind), value, [S("at"), round(x, 4), round(y, 4)], [S("layer"), layer],
            [S("effects"), [S("font"), [S("size"), size, size], [S("thickness"), thick]]]]


def rect(x0, y0, x1, y1, layer, width):
    return [S("fp_rect"), [S("start"), x0, y0], [S("end"), x1, y1],
            [S("stroke"), [S("width"), width], [S("type"), S("solid")]], [S("fill"), S("none")], [S("layer"), layer]]


def main():
    keys, width = layout()
    fp = [S("footprint"), "KEYPAD_20", [S("version"), 20221018], [S("generator"), S("pcbnew")],
          [S("layer"), "F.Cu"],
          [S("descr"), "StyloSynth 20-key piano-layout stylus keypad (A..E), 8 mm naturals, exposed ENIG copper"],
          [S("tags"), "stylophone keypad stylus piano"],
          [S("attr"), S("through_hole"), S("exclude_from_pos_files"), S("exclude_from_bom")],
          text("reference", "K1", 2, -3.5, "F.Fab"),
          text("value", "KEYPAD", width / 2, NATURAL_L + 6, "F.Fab"),
          rect(-1.5, -4.0, width + 1.5, NATURAL_L + 4.0, "F.SilkS", 0.2),
          rect(-2.0, -4.5, width + 2.0, NATURAL_L + 4.5, "F.CrtYd", 0.05)]
    for n, note, kind, g in keys:
        if kind == "sharp":
            fp.append([S("pad"), str(n), S("smd"), S("roundrect"), [S("at"), g["cx"], SHARP_L / 2],
                       [S("size"), SHARP_W, SHARP_L], [S("layers"), "F.Cu", "F.Mask"], [S("roundrect_rratio"), 0.15]])
            fp.append(text("user", note, g["cx"], -2.0, "F.SilkS", 1.0, 0.15))
        else:
            ax, ay = g["cx"], NATURAL_L - 3.0            # anchor inside the wide lower part
            pts = [[S("xy"), round(x - ax, 4), round(y - ay, 4)] for x, y in g["poly"]]
            fp.append([S("pad"), str(n), S("smd"), S("custom"), [S("at"), round(ax, 4), ay], [S("size"), 1, 1],
                       [S("layers"), "F.Cu", "F.Mask"],
                       [S("options"), [S("clearance"), S("outline")], [S("anchor"), S("rect")]],
                       [S("primitives"), [S("gr_poly"), [S("pts")] + pts, [S("width"), 0], [S("fill"), S("yes")]]]])
            fp.append(text("user", note, g["cx"], NATURAL_L + 2.0, "F.SilkS", 1.2, 0.2))
        fp.append([S("pad"), str(n), S("thru_hole"), S("circle"), [S("at"), round(g["via_x"], 4), VIA_Y],
                   [S("size"), VIA_PAD, VIA_PAD], [S("drill"), VIA_DRILL], [S("layers"), "*.Cu", "*.Mask"]])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dumps(fp) + "\n")
    print(f"wrote {OUT.name}: {width:g} x {NATURAL_L:g} mm")
    for n, note, kind, g in keys:
        print(f"  key {n:>2} {note:<2} {kind:<7} via x={g['via_x']:.2f}")


if __name__ == "__main__":
    main()
