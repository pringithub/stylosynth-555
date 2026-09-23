#!/usr/bin/env python3
"""Generate hardware/kicad/stylosynth.kicad_sch (KiCad 7 format) from circuit.py.

Net-label style: every connected pin gets a short wire stub and a local label with the net
name, unused pins get a no-connect flag. Parts are grouped into framed functional blocks.
"""
import datetime
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circuit  # noqa: E402
from sexpr import Sym, dumps, load_lib_symbol, symbol_pins  # noqa: E402

SYMDIR = Path("/usr/share/kicad/symbols")
OUT = circuit.HW / "kicad"
PROJECT = "stylosynth"
GRID = 1.27
STUB = 2.54
CHAR_W = 1.05          # approx label glyph advance at 1.27 mm font
MARGIN = 5.08
BLOCK_ORDER = ["Power", "Oscillator", "Vibrato", "Octave", "Amp", "Keys", "Mechanical"]
BLOCK_WIDTH = {"Keys": 540.0}
DEFAULT_BLOCK_WIDTH = 260.0
PAPERS = [("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841)]
NS = uuid.UUID("7c1f6f0e-4a55-4d1b-9a55-5c1e0e5f5555")
ROOT_UUID = str(uuid.uuid5(NS, "root"))


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(map(str, parts))))


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def S(x):
    return Sym(x)


def font(hide=False, justify=None):
    e = [S("effects"), [S("font"), [S("size"), 1.27, 1.27]]]
    if justify:
        e.append([S("justify")] + [S(j) for j in justify])
    if hide:
        e.append(S("hide"))
    return e


class LibCache:
    def __init__(self):
        self.syms = {}

    def get(self, lib_id):
        if lib_id not in self.syms:
            lib, name = lib_id.split(":")
            self.syms[lib_id] = load_lib_symbol(SYMDIR / f"{lib}.kicad_sym", name)
        return self.syms[lib_id]

    def units(self, lib_id):
        pins = symbol_pins(self.get(lib_id))
        us = sorted({p[0] for p in pins if p[0] > 0})
        return us or [1]

    def pins(self, lib_id, unit):
        return [p for p in symbol_pins(self.get(lib_id)) if p[0] in (0, unit)]

    def lib_symbols_node(self):
        node = [S("lib_symbols")]
        for lib_id, sym in self.syms.items():
            node.append([S("symbol"), lib_id] + [c for c in sym[2:] if not (isinstance(c, list) and c[0] == "extends")])
        return node


OUTWARD = {0: (-1, 0), 90: (0, 1), 180: (1, 0), 270: (0, -1)}   # lib pin angle -> outward dir in sch coords
LABEL_STYLE = {(1, 0): (0, ["left", "bottom"]), (-1, 0): (180, ["right", "bottom"]),
               (0, -1): (90, ["left", "bottom"]), (0, 1): (270, ["right", "bottom"])}


class Unit:
    """One placed symbol unit with its pin geometry relative to the symbol origin (sch coords)."""

    def __init__(self, part, unit, lib):
        self.part, self.unit = part, unit
        self.items = []
        xs, ys = [0.0], [0.0]
        for _, num, _nm, _typ, px, py, ang, _ln in lib.pins(part.lib_id, unit):
            dx, dy = OUTWARD[int(ang) % 360]
            ex, ey = px, -py
            net = part.pins.get(num)
            self.items.append((num, net, ex, ey, dx, dy))
            xs.append(ex)
            ys.append(ey)
            if net is None:
                continue
            tx, ty = ex + dx * STUB, ey + dy * STUB
            text = len(net) * CHAR_W + 1.0
            xs += [tx, tx + dx * text]
            ys += [ty, ty + dy * text]
            if dx == 0:
                xs += [tx - 1.5, tx + 1.5]
            else:
                ys += [ty - 1.5, ty + 1.5]
        vertical_pins = any(dx == 0 for *_, dx, dy in self.items)
        self.text_right = vertical_pins and len(self.items) <= 3
        if self.text_right:
            xs.append(2.54 + max(len(part.ref), len(part.value)) * CHAR_W)
        else:
            ys += [min(ys) - 5.0, max(ys) + 5.0]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        self.w = self.bbox[2] - self.bbox[0] + 2 * GRID
        self.h = self.bbox[3] - self.bbox[1] + 2 * GRID
        self.x = self.y = 0.0

    def place(self, left, top):
        self.x = snap(left - self.bbox[0] + GRID)
        self.y = snap(top - self.bbox[1] + GRID)

    def nodes(self):
        p, x, y = self.part, self.x, self.y
        is_flag = p.lib_id == "power:PWR_FLAG"
        body_ys = [ey for _, _, _, ey, _, _ in self.items] or [0.0]
        body_xs = [ex for _, _, ex, _, _, _ in self.items] or [0.0]
        if self.text_right:
            ref_at, val_at, just = (x + 2.54, y - 1.27), (x + 2.54, y + 1.27), ["left"]
        else:
            ref_at = (x + min(body_xs) + 1.27, y + min(body_ys) - 2.54)
            val_at = (x + min(body_xs) + 1.27, y + max(body_ys) + 3.81)
            just = ["left"]
        sym = [S("symbol"), [S("lib_id"), p.lib_id], [S("at"), x, y, 0], [S("unit"), self.unit],
               [S("in_bom"), S("no" if is_flag or p.ref.startswith("K") else "yes")],
               [S("on_board"), S("no" if is_flag else "yes")], [S("dnp"), S("no")],
               [S("uuid"), uid(p.ref, self.unit)],
               [S("property"), "Reference", p.ref, [S("at"), snap(ref_at[0]), snap(ref_at[1]), 0], font(is_flag, just)],
               [S("property"), "Value", p.value, [S("at"), snap(val_at[0]), snap(val_at[1]), 0], font(is_flag, just)],
               [S("property"), "Footprint", p.footprint, [S("at"), x, y, 0], font(True)],
               [S("property"), "Datasheet", "~", [S("at"), x, y, 0], font(True)]]
        for k, v in (("Description", p.desc), ("MPN", p.mpn), ("Block", p.block)):
            if v:
                sym.append([S("property"), k, v, [S("at"), x, y, 0], font(True)])
        for num, *_ in self.items:
            sym.append([S("pin"), num, [S("uuid"), uid(p.ref, self.unit, "pin", num)]])
        sym.append([S("instances"), [S("project"), PROJECT,
                    [S("path"), f"/{ROOT_UUID}", [S("reference"), p.ref], [S("unit"), self.unit]]]])
        out = [sym]
        for num, net, ex, ey, dx, dy in self.items:
            px, py = snap(x + ex), snap(y + ey)
            if net is None:
                out.append([S("no_connect"), [S("at"), px, py], [S("uuid"), uid(p.ref, self.unit, "nc", num)]])
                continue
            tx, ty = snap(px + dx * STUB), snap(py + dy * STUB)
            out.append([S("wire"), [S("pts"), [S("xy"), px, py], [S("xy"), tx, ty]],
                        [S("stroke"), [S("width"), 0], [S("type"), S("default")]],
                        [S("uuid"), uid(p.ref, self.unit, "w", num)]])
            ang, just = LABEL_STYLE[(dx, dy)]
            out.append([S("label"), net, [S("at"), tx, ty, ang], [S("fields_autoplaced")], font(False, just),
                        [S("uuid"), uid(p.ref, self.unit, "l", num)]])
        return out


def layout_block(units, width):
    x = y = 0.0
    row_h = 0.0
    for u in units:
        if x > 0 and x + u.w > width:
            x, y = 0.0, y + row_h + MARGIN
            row_h = 0.0
        u.place(x, y)
        x += u.w + MARGIN
        row_h = max(row_h, u.h)
    return max((u.x + u.bbox[2] for u in units), default=0) + GRID, y + row_h


def main():
    lib = LibCache()
    flags = [circuit.Part(f"#FLG0{101 + i}", "power:PWR_FLAG", "PWR_FLAG", "", {"1": net}, "Power")
             for i, net in enumerate(circuit.PWR_FLAG_NETS)]
    blocks = {b: [] for b in BLOCK_ORDER}
    for part in circuit.PARTS + flags:
        for u in lib.units(part.lib_id):
            blocks[part.block].append(Unit(part, u, lib))

    # place blocks in a flow on the sheet
    title_h = 10.16
    placed, x, y, row_h, sheet_w = [], 20.32, 20.32, 0.0, 560.0
    for name in BLOCK_ORDER:
        units = blocks[name]
        bw, bh = layout_block(units, BLOCK_WIDTH.get(name, DEFAULT_BLOCK_WIDTH))
        bw, bh = bw + 2 * MARGIN, bh + 2 * MARGIN + title_h
        if x > 20.32 and x + bw > sheet_w + 20.32:
            x, y, row_h = 20.32, y + row_h + 2 * MARGIN, 0.0
        for u in units:
            u.x, u.y = snap(u.x + x + MARGIN), snap(u.y + y + MARGIN + title_h)
        placed.append((name, x, y, bw, bh, units))
        x += bw + 2 * MARGIN
        row_h = max(row_h, bh)
    need_w = max(bx + bw for _, bx, _, bw, _, _ in placed) + 20
    need_h = max(by + bh for _, _, by, _, bh, _ in placed) + 40
    paper = next(p for p in PAPERS if p[1] >= need_w and p[2] >= need_h)

    items = []
    for name, bx, by, bw, bh, units in placed:
        items.append([S("rectangle"), [S("start"), snap(bx), snap(by)], [S("end"), snap(bx + bw), snap(by + bh)],
                      [S("stroke"), [S("width"), 0.3], [S("type"), S("dash")]], [S("fill"), [S("type"), S("none")]],
                      [S("uuid"), uid("frame", name)]])
        items.append([S("text"), name.upper(), [S("at"), snap(bx + MARGIN), snap(by + 7.62), 0],
                      [S("effects"), [S("font"), [S("size"), 3, 3], S("bold")], [S("justify"), S("left"), S("bottom")]],
                      [S("uuid"), uid("title", name)]])
        for u in units:
            items.extend(u.nodes())

    sch = [S("kicad_sch"), [S("version"), 20230121], [S("generator"), S("eeschema")],
           [S("uuid"), ROOT_UUID], [S("paper"), paper[0]],
           [S("title_block"), [S("title"), "StyloSynth-555 stylus synthesizer"],
            [S("date"), datetime.date.today().isoformat()], [S("rev"), "1.0"],
            [S("comment"), 1, "Generated by hardware/scripts/gen_schematic.py - edit circuit.py, not this file"]],
           lib.lib_symbols_node()]
    sch += items
    sch.append([S("sheet_instances"), [S("path"), "/", [S("page"), "1"]]])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{PROJECT}.kicad_sch").write_text(dumps(sch) + "\n")
    pro = OUT / f"{PROJECT}.kicad_pro"
    if not pro.exists():
        pro.write_text(json.dumps({"meta": {"filename": f"{PROJECT}.kicad_pro", "version": 1}}, indent=2))
    (OUT / "fp-lib-table").write_text(
        '(fp_lib_table\n  (version 7)\n  (lib (name "StyloSynth")(type "KiCad")(uri "${KIPRJMOD}/lib/StyloSynth.pretty")'
        '(options "")(descr "Project footprints"))\n)\n')
    print(f"wrote {OUT / (PROJECT + '.kicad_sch')} on {paper[0]} "
          f"({sum(len(b[5]) for b in placed)} symbol units)")


if __name__ == "__main__":
    main()
