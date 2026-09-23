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
BOARD_W, BOARD_H, CORNER_R = 136.0, 98.0, 3.0
KEYPAD_ORIGIN = (20.0, 57.0)  # top-left of the 96 x 36 mm keyboard
LADDER_Y = 49.5              # single row of vertical ladder resistors above the key vias
POWER_NETS = ["GND", "+9V", "+5V", "VSW_IN", "DC_IN", "BAT_P", "V_FILT", "AMP_OUT", "SPK_DRV", "SPK_P", "HP"]

# ref -> (x, y, rotation_deg, side, anchor)
# anchor: "center" = bbox centre, "top" = bbox top at y, "right" = bbox right edge at x, "origin" = fp origin
PLACEMENT = {
    # top edge: jacks + panel controls
    "J1": (6.8, 0.0, 180, "F", "top"), "SW1": (18.8, 6, 0, "F", "center"), "D2": (27.5, 6, 0, "F", "center"),
    "RV3": (38.2, 8, 0, "F", "center"), "SW5": (51.8, 6, 0, "F", "center"), "SW2": (62.8, 6, 0, "F", "center"),
    "SW3": (73.8, 6, 0, "F", "center"), "SW4": (84.8, 6, 0, "F", "center"), "RV1": (98.2, 8, 0, "F", "center"),
    "J4": (111.6, 0.0, 0, "F", "top"), "J3": (122.6, 0.0, 0, "F", "top"),
    # vibrato LFO
    "U5": (14, 26, 0, "F", "center"), "C18": (13.5, 35.5, 0, "F", "center"), "RV2": (14, 42, 0, "F", "center"),
    "R10": (22.5, 25, 90, "F", "center"), "R11": (26, 25, 90, "F", "center"), "R12": (29.5, 25, 90, "F", "center"),
    "R13": (33, 25, 90, "F", "center"), "R14": (36.5, 25, 90, "F", "center"), "C17": (22.5, 36, 90, "F", "center"),
    "C19": (28, 35, 0, "F", "center"), "C20": (34.5, 35, 0, "F", "center"),
    # octave divider
    "U3": (46, 32, 0, "F", "center"), "C9": (54, 26, 90, "F", "center"),
    # audio + amp
    "R7": (58.5, 25, 90, "F", "center"), "C10": (58.5, 36, 90, "F", "center"), "C11": (63, 36, 90, "F", "center"),
    "U4": (71, 27, 0, "F", "center"), "C12": (70, 38, 0, "F", "center"), "C13": (80.5, 25, 0, "F", "center"),
    "C14": (78, 37, 90, "F", "center"), "R8": (83, 36, 90, "F", "center"), "C15": (87, 37, 90, "F", "center"),
    "C16": (90, 26, 0, "F", "center"), "R9": (92, 37, 90, "F", "center"), "J5": (99, 38, 0, "B", "center"),
    # oscillator
    "U2": (106, 27, 0, "F", "center"), "C6": (114, 25, 90, "F", "center"), "C7": (121, 24, 0, "F", "center"),
    "R3": (127, 25, 90, "F", "center"), "R4": (118, 31, 90, "F", "center"), "R5": (121.5, 31, 90, "F", "center"),
    "C8": (127, 32, 0, "F", "center"), "RV5": (123, 39, 0, "F", "center"), "R6": (133, 38, 90, "F", "center"),
    "RV4": (123, 56, 90, "F", "center"),
    # power (left of the keyboard)
    "D1": (5, 50, 90, "F", "center"), "C1": (12, 50, 0, "F", "center"), "C2": (5, 60, 90, "F", "center"),
    "C3": (12, 60, 0, "F", "center"), "R2": (5, 69, 90, "F", "center"), "U1": (12, 69, 0, "F", "center"),
    "R1": (5, 77, 90, "F", "center"), "C4": (12, 77, 0, "F", "center"), "C5": (5, 84, 90, "F", "center"),
    "J2": (12.5, 87, 0, "B", "center"),
    # keys
    "K1": (KEYPAD_ORIGIN[0], KEYPAD_ORIGIN[1], 0, "F", "origin"),
    # mounting holes
    "H1": (4, 23, 0, "F", "center"), "H2": (132, 46, 0, "F", "center"), "H3": (4, 94, 0, "F", "center"),
    "H4": (132, 94, 0, "F", "center"),
}
_VIA_X = {n: g["via_x"] for n, _note, _kind, g in gen_keypad.layout()[0]}
for seg in circuit.LADDER["segments"]:
    PLACEMENT[f"R{101 + seg['segment']}"] = (KEYPAD_ORIGIN[0] + _VIA_X[seg["key"]], LADDER_Y, 90, "F", "center")

SILK_TEXT = [  # (text, x, y, size_mm)
    ("StyloSynth", 127, 68, 1.8), ("555  v1.2", 127, 72, 1.4),
    ("9V DC (-)", 6.8, 17.5, 0.9), ("ON", 18.8, 11, 0.9), ("DEPTH", 38.2, 16.5, 0.9), ("VIB", 51.8, 11, 0.9),
    ("OCT-1", 62.8, 11, 0.9), ("OCT-2", 73.8, 11, 0.9), ("SOFT", 84.8, 11, 0.9), ("VOLUME", 98.2, 16.5, 0.9),
    ("PHONES", 111.6, 20.5, 0.9), ("STYLUS", 122.6, 20.5, 0.9), ("RATE", 21, 45.5, 0.9),
    ("TUNE", 127.5, 62.5, 0.9), ("SPAN", 116, 39, 0.9),
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
