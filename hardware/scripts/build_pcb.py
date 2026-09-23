#!/usr/bin/env python3
"""Build hardware/kicad/stylosynth.kicad_pcb from circuit.py.

Stages (run all by default):
  place   - project rules, outline, footprints, nets, silkscreen, pour keep-out -> DSN export
  route   - Freerouting (headless) DSN -> SES
  finish  - import SES tracks/vias, GND pours both layers, fill, save, DRC report
Usage: .venv/bin/python hardware/scripts/build_pcb.py [place|route|finish|all]
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circuit  # noqa: E402
import gen_keypad  # noqa: E402
from gen_schematic import uid  # noqa: E402
from sexpr import find, find1, parse  # noqa: E402

KICAD = circuit.HW / "kicad"
PCB = KICAD / "stylosynth.kicad_pcb"
PRO = KICAD / "stylosynth.kicad_pro"
DSN = KICAD / "stylosynth.dsn"
SES = KICAD / "stylosynth.ses"
DRC = KICAD / "drc_report.txt"
ROOT = circuit.HW.parent
FREEROUTING = ROOT / "tools" / "freerouting-2.1.0.jar"
FPDIRS = {"StyloSynth": KICAD / "lib" / "StyloSynth.pretty"}

ORIGIN = (50.0, 40.0)        # board top-left in KiCad page coordinates (mm)
BOARD_W, BOARD_H, CORNER_R = 170.0, 108.0, 3.0
KEYPAD_ORIGIN = (37.0, 58.0)  # top-left of the 96 x 36 mm keyboard
LADDER_ROWS = (45.0, 50.5)   # staggered rows of vertical ladder resistors above the keys
POWER_NETS = ["GND", "+9V", "+5V", "VSW_IN", "DC_IN", "BAT_P", "V_FILT", "AMP_OUT", "SPK_DRV", "SPK_P", "HP"]

# ref -> (x, y, rotation_deg, side, anchor)
# anchor: "center" = bbox centre, "top" = bbox top at y, "right" = bbox right edge at x, "origin" = fp origin
PLACEMENT = {
    # top edge: jacks + panel controls
    "J1": (12, 0.0, 180, "F", "top"), "SW1": (26, 7, 0, "F", "center"), "D2": (34, 7, 0, "F", "center"),
    "RV3": (46, 9, 0, "F", "center"), "SW5": (60, 7, 0, "F", "center"), "SW2": (71, 7, 0, "F", "center"),
    "SW3": (82, 7, 0, "F", "center"), "SW4": (93, 7, 0, "F", "center"), "RV1": (108, 9, 0, "F", "center"),
    "J4": (126, 0.0, 0, "F", "top"), "J3": (170.0, 62, 270, "F", "right"),
    # vibrato LFO
    "U5": (18, 30, 0, "F", "center"), "C17": (9, 22, 90, "F", "center"), "R10": (31, 21, 0, "F", "center"),
    "R11": (31, 25, 0, "F", "center"), "R12": (31, 29, 0, "F", "center"), "R13": (31, 33, 0, "F", "center"),
    "RV2": (31, 38.5, 0, "F", "center"), "C18": (8.5, 37.5, 0, "F", "center"), "C19": (43, 23, 0, "F", "center"),
    "R14": (43, 37.5, 0, "F", "center"), "C20": (43, 30, 0, "F", "center"),
    # octave divider
    "U3": (57, 30, 0, "F", "center"), "C9": (65, 22, 90, "F", "center"),
    # audio + amp
    "R7": (75, 21, 0, "F", "center"), "C10": (75, 27, 0, "F", "center"), "C11": (75, 33, 0, "F", "center"),
    "U4": (89, 30, 0, "F", "center"), "C12": (83, 39, 0, "F", "center"), "C13": (100, 23, 0, "F", "center"),
    "C14": (100, 35, 90, "F", "center"), "R8": (106.5, 30, 90, "F", "center"), "C15": (107, 39, 0, "F", "center"),
    "C16": (114, 24, 0, "F", "center"), "R9": (114.5, 34, 90, "F", "center"), "J5": (126, 31, 0, "B", "center"),
    # oscillator (right of the keyboard)
    "U2": (147, 30, 0, "F", "center"), "C6": (139, 22, 90, "F", "center"), "C7": (160, 23, 0, "F", "center"),
    "R3": (160, 29, 0, "F", "center"), "R4": (160, 34, 0, "F", "center"), "R5": (160, 38.5, 0, "F", "center"),
    "RV5": (158, 45, 0, "F", "center"), "C8": (139, 38, 90, "F", "center"), "R6": (157, 53, 0, "F", "center"),
    "RV4": (143, 50, 0, "F", "center"),
    # power (left of the keyboard)
    "D1": (17, 47, 0, "F", "center"), "C1": (11, 57, 0, "F", "center"), "C2": (24, 57, 90, "F", "center"),
    "R1": (18, 63.5, 0, "F", "center"), "R2": (18, 68, 0, "F", "center"), "C3": (10, 75, 0, "F", "center"),
    "U1": (21, 75, 0, "F", "center"), "C4": (29, 75, 0, "F", "center"), "C5": (18, 83, 0, "F", "center"),
    "J2": (16, 93, 0, "B", "center"),
    # keys
    "K1": (KEYPAD_ORIGIN[0], KEYPAD_ORIGIN[1], 0, "F", "origin"),
    # mounting holes
    "H1": (4, 4, 0, "F", "center"), "H2": (166, 4, 0, "F", "center"), "H3": (4, 104, 0, "F", "center"),
    "H4": (166, 104, 0, "F", "center"), "H5": (85, 104, 0, "F", "center"), "H6": (164, 84, 0, "F", "center"),
}
_VIA_X = {n: g["via_x"] for n, _note, _kind, g in gen_keypad.layout()[0]}
for seg in circuit.LADDER["segments"]:
    PLACEMENT[f"R{101 + seg['segment']}"] = (KEYPAD_ORIGIN[0] + _VIA_X[seg["key"]],
                                             LADDER_ROWS[seg["key"] % 2], 90, "F", "center")

SILK_TEXT = [  # (text, x, y, size_mm)
    ("StyloSynth-555", 60, 101.5, 2.5), ("v1.1", 112, 101.5, 1.5),
    ("VIBRATO LFO", 25, 17.5, 1.2), ("OCTAVE", 57, 17.5, 1.2), ("AMP", 92, 17.5, 1.2),
    ("OSCILLATOR", 150, 17.5, 1.2), ("POWER", 17, 43, 1.2),
    ("9V DC (-)", 12, 16.0, 1.0), ("ON", 26, 11.5, 1.0), ("DEPTH", 46, 16.5, 1.0), ("VIB", 60, 11.5, 1.0),
    ("OCT-1", 71, 11.5, 1.0), ("OCT-2", 82, 11.5, 1.0), ("SOFT", 93, 11.5, 1.0), ("VOLUME", 108, 16.5, 1.0),
    ("PHONES", 126, 20.5, 1.0), ("STYLUS", 160, 69, 1.0), ("RATE", 31, 42, 1.0),
    ("TUNE (key 20)", 143, 54.5, 1.0), ("SPAN (key 1)", 158, 49.5, 1.0),
]


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))


# ---------------------------------------------------------------------------------------------
def write_project():
    def cls(name, clearance, width, via_d, via_drill):
        return {"name": name, "clearance": clearance, "track_width": width, "via_diameter": via_d,
                "via_drill": via_drill, "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_width": 0.2,
                "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12,
                "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"}
    pro = json.loads(PRO.read_text()) if PRO.exists() else {}
    pro["meta"] = {"filename": PRO.name, "version": 1}
    pro["net_settings"] = {
        "classes": [cls("Default", 0.2, 0.3, 0.8, 0.4), cls("Power", 0.2, 0.6, 1.0, 0.5)],
        "meta": {"version": 3}, "net_colors": None, "netclass_assignments": None,
        "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in POWER_NETS]}
    ds = pro.setdefault("board", {}).setdefault("design_settings", {})
    # JLCPCB standard 2-layer capabilities with margin
    ds["rules"] = {"allow_blind_buried_vias": False, "allow_microvias": False, "max_error": 0.005,
                   "min_clearance": 0.2, "min_copper_edge_clearance": 0.5, "min_hole_clearance": 0.25,
                   "min_hole_to_hole": 0.5, "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1,
                   "min_silk_clearance": 0.0, "min_through_hole_diameter": 0.3, "min_track_width": 0.2,
                   "min_via_annular_width": 0.13, "min_via_diameter": 0.6, "solder_mask_clearance": 0.0,
                   "solder_mask_min_width": 0.0, "solder_paste_clearance": 0.0, "solder_paste_margin_ratio": 0.0}
    ds["track_widths"] = [0.0, 0.3, 0.6, 1.0]
    ds["via_dimensions"] = [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.8, "drill": 0.4},
                            {"diameter": 1.0, "drill": 0.5}]
    PRO.write_text(json.dumps(pro, indent=2))


def add_outline(board):
    w, h, r = BOARD_W, BOARD_H, CORNER_R

    def seg(a, b):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(*a))
        s.SetEnd(pt(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    def arc(start, mid, end):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(pt(*start), pt(*mid), pt(*end))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    k = r * (1 - 0.70710678)
    seg((r, 0), (w - r, 0))
    arc((w - r, 0), (w - k, k), (w, r))
    seg((w, r), (w, h - r))
    arc((w, h - r), (w - k, h - k), (w - r, h))
    seg((w - r, h), (r, h))
    arc((r, h), (k, h - k), (0, h - r))
    seg((0, h - r), (0, r))
    arc((0, r), (k, k), (r, 0))


def load_fp(fpid):
    lib, name = fpid.split(":")
    path = FPDIRS.get(lib, Path(f"/usr/share/kicad/footprints/{lib}.pretty"))
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def place_fp(fp, x, y, rot, side, anchor):
    fp.SetPosition(pt(0, 0))
    fp.SetOrientationDegrees(rot)
    if side == "B":
        fp.Flip(fp.GetPosition(), False)
    if anchor == "origin":
        fp.SetPosition(pt(x, y))
        return
    bb = fp.GetBoundingBox(False, False)
    cx, top = bb.GetCenter().x, bb.GetTop()
    dy = mm(ORIGIN[1] + y) - (top if anchor == "top" else bb.GetCenter().y)
    dx = mm(ORIGIN[0] + x) - (bb.GetRight() if anchor == "right" else cx)
    fp.SetPosition(pcbnew.VECTOR2I(fp.GetPosition().x + dx, fp.GetPosition().y + dy))


def add_text(board, text, x, y, size):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pt(x, y))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.15, size * 0.15)))
    board.Add(t)


def add_zone(board, layer, net, rule_area=False, rect=None):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    x0, y0, x1, y1 = rect or (0.3, 0.3, BOARD_W - 0.3, BOARD_H - 0.3)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        p = pt(x, y)
        ol.Append(p.x, p.y)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowTracks(False)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNetCode(net.GetNetCode())
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(mm(0.5))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def stage_place():
    write_project()
    for f in (PCB, KICAD / "stylosynth.kicad_prl"):
        if f.exists():
            f.unlink()
    board = pcbnew.NewBoard(str(PCB))
    board.SetCopperLayerCount(2)
    add_outline(board)

    nets = {}
    for name in sorted(circuit.nets()):
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n

    for part in circuit.PARTS:
        if part.ref not in PLACEMENT:
            raise SystemExit(f"no placement for {part.ref}")
        fp = load_fp(part.footprint)
        fp.SetReference(part.ref)
        fp.SetValue(part.value)
        fp.SetPath(pcbnew.KIID_PATH(f"/{uid(part.ref, 1)}"))
        for pad in fp.Pads():
            net = part.pins.get(pad.GetNumber())
            if net:
                pad.SetNet(nets[net])
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        ref.SetTextThickness(mm(0.12))
        if part.ref.startswith(("H", "K")):
            ref.SetVisible(False)
        board.Add(fp)
        place_fp(fp, *PLACEMENT[part.ref])

    for text, x, y, size in SILK_TEXT:
        add_text(board, text, x, y, size)
    # keep GND pour out from between the exposed keys
    add_zone(board, pcbnew.F_Cu, None, rule_area=True,
             rect=(KEYPAD_ORIGIN[0] - 2, KEYPAD_ORIGIN[1] - 4, KEYPAD_ORIGIN[0] + 98, KEYPAD_ORIGIN[1] + 40))
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(PCB), board)
    if not pcbnew.ExportSpecctraDSN(board, str(DSN)):
        raise SystemExit("DSN export failed")
    print(f"placed {len(circuit.PARTS)} footprints, saved {PCB.name}, exported {DSN.name}")


def stage_route(passes=100):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GTK_", "GIO_", "GSETTINGS", "LOCPATH", "SNAP"))}
    cmd = ["java", "-Djava.awt.headless=true", "-jar", str(FREEROUTING), "-de", str(DSN), "-do", str(SES),
           "-mp", str(passes), "--gui.enabled=false"]
    print(" ".join(cmd))
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
    log = (proc.stdout + proc.stderr).splitlines()
    (KICAD / "freerouting.log").write_text("\n".join(log))
    for line in log:
        if re.search(r"(pass|unrouted|completed|finished|error)", line, re.I) and "Exception" not in line:
            print("  ", line[:160])
    if not SES.exists():
        raise SystemExit("Freerouting produced no SES file (see freerouting.log)")


def import_ses(board):
    root = parse(SES.read_text())
    routes = find1(root, "routes")
    res = find1(routes, "resolution")
    unit, per = str(res[1]).lower(), float(res[2])
    to_nm = {"um": 1000.0, "mm": 1e6, "mil": 25400.0, "inch": 25.4e6}[unit] / per
    nets = {n.GetNetname(): n for n in board.GetNetsByName().values()}
    layers = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    n_tracks = n_vias = 0

    def xy(x, y):
        return pcbnew.VECTOR2I(int(round(float(x) * to_nm)), int(round(-float(y) * to_nm)))

    for net in find(find1(routes, "network_out"), "net"):
        ni = nets.get(str(net[1]))
        if ni is None:
            raise SystemExit(f"SES net {net[1]} not on board")
        for wire in find(net, "wire"):
            path = find1(wire, "path")
            layer, width, coords = layers[str(path[1])], float(path[2]) * to_nm, path[3:]
            pts = [xy(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]
            for a, b in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(a)
                t.SetEnd(b)
                t.SetWidth(int(width))
                t.SetLayer(layer)
                t.SetNet(ni)
                board.Add(t)
                n_tracks += 1
        for via in find(net, "via"):
            m = re.search(r"_(\d+):(\d+)_um", str(via[1]))
            dia, drill = (int(m.group(1)) * 1000, int(m.group(2)) * 1000) if m else (mm(0.8), mm(0.4))
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(xy(via[2], via[3]))
            v.SetWidth(dia)
            v.SetDrill(drill)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(ni)
            board.Add(v)
            n_vias += 1
    return n_tracks, n_vias


def stage_finish():
    board = pcbnew.LoadBoard(str(PCB))
    for t in list(board.GetTracks()):
        board.Remove(t)
    for z in [z for z in board.Zones() if not z.GetIsRuleArea()]:
        board.Remove(z)
    n_tracks, n_vias = import_ses(board)
    gnd = board.FindNet("GND")
    add_zone(board, pcbnew.F_Cu, gnd)
    add_zone(board, pcbnew.B_Cu, gnd)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(PCB), board)
    print(f"imported {n_tracks} track segments, {n_vias} vias; poured GND on both layers")
    report_drc(board)


def report_drc(board):
    """Summarise the DRC report by violation type and severity (library-table warnings are expected headless)."""
    pcbnew.WriteDRCReport(board, str(DRC), pcbnew.EDA_UNITS_MILLIMETRES, True)
    counts = {}
    for kind, sev in re.findall(r"^\[(\w+)\]:.*\n.*Severity: (\w+)", DRC.read_text(), re.M):
        counts[(kind, sev)] = counts.get((kind, sev), 0) + 1
    errors = {k: v for k, v in counts.items() if k[1] == "error"}
    warnings = {k: v for k, v in counts.items() if k[1] != "error" and k[0] != "lib_footprint_issues"}
    print(f"DRC errors: {errors or 'none'}")
    print(f"DRC warnings: {warnings or 'none'}  (full report: {DRC.relative_to(ROOT)})")
    return errors


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("place", "all"):
        stage_place()
    if stage in ("route", "all"):
        stage_route()
    if stage in ("finish", "all"):
        stage_finish()
    if stage == "drc":
        report_drc(pcbnew.LoadBoard(str(PCB)))


if __name__ == "__main__":
    main()
