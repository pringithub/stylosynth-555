#!/usr/bin/env python3
"""Extract PCB geometry for the enclosure build and generate the laser-cut acrylic DXFs.

Run with the project venv (needs KiCad pcbnew, shapely, ezdxf, Pillow):
    .venv/bin/python enclosure/gen_geometry.py
Outputs (enclosure/out/):
    pcb_geometry.json    board outline, holes, components (body boxes, heights, pads) for Blender
    enclosure.json       shared enclosure parameters + acrylic layer polygons for Blender
    textures/pcb_top.png, pcb_bottom.png   board artwork rendered from the KiCad layers
    acrylic/*.dxf        laser-cut files (mm)
Also runs a fit check of internal parts against the PCB underside and exits non-zero on collision.
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import ezdxf
import pcbnew
from PIL import Image, ImageChops
from shapely.affinity import translate
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hardware" / "scripts"))
from build_pcb import BOARD_H, BOARD_W, CORNER_R, ORIGIN, PCB  # noqa: E402

import os  # noqa: E402
PCB = Path(os.environ.get("STYLOSYNTH_PCB", PCB))
OUT = Path(os.environ.get("STYLOSYNTH_ENC_OUT", ROOT / "enclosure" / "out"))
TEX_PX_PER_MM = 16

# ---- shared mechanical parameters (mm) -----------------------------------------------------
P = {
    "pcb_t": 1.6,
    "pcb_clear": 0.5,              # gap between PCB edge and enclosure wall
    "lead_len": 1.8,               # THT lead protrusion below the PCB
    "pcb_bottom_z": 24.0,          # printed tray: PCB underside height above the tray base
    "tray_wall": 2.4, "tray_floor": 2.0,
    "boss_d": 7.0, "insert_d": 4.0, "insert_depth": 5.7,   # M3 x 5.7 heat-set inserts
    "battery": [48.5, 26.5, 17.5], "battery_xy": [22.0, 58.0],   # 9V block, board coords of its top-left
    "speaker_d": 40.0, "speaker_h": 6.0, "speaker_xy": [104.0, 73.0],
    "support_pillars": [[45.0, 90.0], [82.0, 92.0]],       # unscrewed PCB supports under the keyboard
    "jack_notches": [],                                   # jacks sit above the wall/frame top, no notches needed
    "feet_d": 10.5, "feet_inset": 11.0,
    "stylus_d": 10.0, "stylus_len": 110.0,
    # acrylic stack: bottom plate + rings, PCB floats 1 mm above the rings on 25 mm M3 standoffs
    "acr_t": 3.0, "acr_rings": 8, "acr_frame_w": 7.0, "acr_standoff": 25.0,
    "acr_bolt_d": 3.2, "acr_corner_bolt_inset": 3.5,
}


def mm(v):
    return pcbnew.ToMM(v)


def board_xy(p):
    return (round(mm(p.x) - ORIGIN[0], 4), round(mm(p.y) - ORIGIN[1], 4))


def rounded_rect(w, h, r, offset=0.0):
    return box(r, r, w - r, h - r).buffer(r + offset, quad_segs=16)


# body height above/below the board (mm) by footprint name
HEIGHTS = [
    ("DIP-16", 8.5), ("DIP-8", 8.5), ("R_Axial", 9.0), ("C_Disc", 6.5), ("C_Rect_L7.2mm_W5.5", 10.0),
    ("C_Rect", 8.0), ("CP_Radial_D8.0", 12.0), ("CP_Radial", 11.5), ("TO-92", 5.2), ("LED_D3.0", 5.5),
    ("DO-41", 8.0), ("3296W", 10.0), ("RK09K", 22.0), ("JS202011", 6.5), ("SJ1-3535", 5.2),
    ("PJ-102AH", 11.0), ("JST_XH", 7.0),
]


def component_height(fpid):
    return next((h for key, h in HEIGHTS if key in fpid), 5.0)


def layer_bbox(fp, layer_names):
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayerName() in layer_names:
            b = g.GetBoundingBox()
            xs += [b.GetLeft(), b.GetRight()]
            ys += [b.GetTop(), b.GetBottom()]
    if not xs:
        b = fp.GetBoundingBox(False, False)
        xs, ys = [b.GetLeft(), b.GetRight()], [b.GetTop(), b.GetBottom()]
    x0, y0 = board_xy(pcbnew.VECTOR2I(min(xs), min(ys)))
    x1, y1 = board_xy(pcbnew.VECTOR2I(max(xs), max(ys)))
    return [x0, y0, x1, y1]


def extract_pcb(board):
    comps, holes = [], []
    for fp in board.Footprints():
        fpid = fp.GetFPIDAsString()
        ref = fp.GetReference()
        side = "B" if fp.IsFlipped() else "F"
        if "MountingHole" in fpid:
            holes.append({"ref": ref, "xy": board_xy(fp.GetPosition()), "d": 3.2})
            continue
        pads = [{"num": p.GetNumber(), "xy": board_xy(p.GetPosition()), "drill": round(mm(p.GetDrillSize().x), 3)}
                for p in fp.Pads()]
        comps.append({
            "ref": ref, "value": fp.GetValue(), "fpid": fpid, "side": side,
            "xy": board_xy(fp.GetPosition()), "rot": round(fp.GetOrientationDegrees(), 2),
            "body": layer_bbox(fp, {f"{side}.Fab"}), "courtyard": layer_bbox(fp, {f"{side}.CrtYd"}),
            "height": component_height(fpid), "pads": pads,
        })
    return {"board": {"w": BOARD_W, "h": BOARD_H, "r": CORNER_R, "t": P["pcb_t"]}, "holes": holes, "components": comps}


# ---- board artwork textures -------------------------------------------------------------------
def render_layer(layer):
    """Layer as a white-on-black mask cropped to the board, in top-view orientation."""
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "l.pdf"
        subprocess.run(["kicad-cli", "pcb", "export", "pdf", "--layers", layer, "--black-and-white",
                        "-o", str(pdf), str(PCB)], check=True, capture_output=True)
        dpi = TEX_PX_PER_MM * 25.4
        subprocess.run(["pdftoppm", "-png", "-r", f"{dpi:g}", "-gray", "-singlefile", str(pdf), str(Path(td) / "l")],
                       check=True)
        img = Image.open(Path(td) / "l.png").convert("L")
    crop = (round(ORIGIN[0] * TEX_PX_PER_MM), round(ORIGIN[1] * TEX_PX_PER_MM),
            round((ORIGIN[0] + BOARD_W) * TEX_PX_PER_MM), round((ORIGIN[1] + BOARD_H) * TEX_PX_PER_MM))
    return ImageChops.invert(img.crop(crop))            # white = drawn


def compose_texture(prefix):
    cu, mask, silk = (render_layer(f"{prefix}.{n}") for n in ("Cu", "Mask", "SilkS"))
    size = cu.size
    base = Image.new("RGB", size, (18, 18, 22))                     # black solder mask
    base.paste(Image.new("RGB", size, (38, 38, 44)), mask=cu)       # copper under mask
    exposed = ImageChops.multiply(cu, mask)
    base.paste(Image.new("RGB", size, (214, 176, 84)), mask=exposed)  # ENIG gold
    silk_vis = ImageChops.subtract(silk, mask)
    base.paste(Image.new("RGB", size, (236, 236, 232)), mask=silk_vis)
    return base


# ---- acrylic stack ------------------------------------------------------------------------------
def acrylic_layers(geo):
    inner = rounded_rect(BOARD_W, BOARD_H, CORNER_R, P["pcb_clear"])
    outer = rounded_rect(BOARD_W, BOARD_H, CORNER_R, P["pcb_clear"] + P["acr_frame_w"])
    # bolt on the corner diagonal, halfway through the frame, so it can't break through the rounded edge
    r_mid = CORNER_R + P["pcb_clear"] + P["acr_frame_w"] / 2
    d = CORNER_R - r_mid / math.sqrt(2)
    bolts = [(d, d), (BOARD_W - d, d), (d, BOARD_H - d), (BOARD_W - d, BOARD_H - d)]
    bolt_holes = unary_union([Point(x, y).buffer(P["acr_bolt_d"] / 2, quad_segs=12) for x, y in bolts])
    frame = outer.difference(inner)
    for x, y in bolts:
        if not frame.buffer(-0.8).contains(Point(x, y).buffer(P["acr_bolt_d"] / 2)):
            raise SystemExit(f"acrylic bolt at {x:.2f},{y:.2f} is too close to a frame edge")

    ring = outer.difference(inner).difference(bolt_holes)
    notches = []
    for ref in P["jack_notches"]:
        comp = next(cp for cp in geo["components"] if cp["ref"] == ref)
        cx = (comp["body"][0] + comp["body"][2]) / 2
        notches.append(box(cx - 5.5, -P["pcb_clear"] - P["acr_frame_w"] - 1, cx + 5.5, 0.1))
    ring_top = ring.difference(unary_union(notches)) if notches else None

    sx, sy = P["speaker_xy"]
    grille, pitch, r_g = [], 4.2, P["speaker_d"] / 2 - 4
    for j in range(-6, 7):
        for i in range(-6, 7):
            x = sx + (i + (j % 2) * 0.5) * pitch
            y = sy + j * pitch * math.sqrt(3) / 2
            if math.hypot(x - sx, y - sy) <= r_g:
                grille.append(Point(x, y).buffer(1.5, quad_segs=8))
    bx, by = P["battery_xy"]
    bw, bh, _ = P["battery"]
    straps = [box(bx + 8, by - 4.5, bx + 8 + 3, by - 1.5).union(box(bx + 8, by + bh + 1.5, bx + 11, by + bh + 4.5)),
              box(bx + bw - 11, by - 4.5, bx + bw - 8, by - 1.5).union(
                  box(bx + bw - 11, by + bh + 1.5, bx + bw - 8, by + bh + 4.5))]
    standoff_holes = [Point(*h["xy"]).buffer(P["acr_bolt_d"] / 2, quad_segs=12) for h in geo["holes"]]
    bottom = outer.difference(unary_union([bolt_holes, *standoff_holes, *grille, *straps]))
    layers = {"bottom_plate": (bottom, 1)}
    if ring_top is None:
        layers["ring"] = (ring, P["acr_rings"])
    else:
        layers.update({"ring": (ring, P["acr_rings"] - 1), "ring_top": (ring_top, 1)})
    return layers, bolts


def write_dxf(poly, path):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    polys = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
    for pg in polys:
        for ring in [pg.exterior, *pg.interiors]:
            # DXF uses Y up; flip so the drawing matches the PCB top view
            msp.add_lwpolyline([(x, -y) for x, y in ring.coords], close=True, dxfattribs={"layer": "CUT"})
    doc.saveas(path)


def poly_rings(poly):
    polys = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
    return [{"outer": [list(map(lambda v: round(v, 4), c)) for c in pg.exterior.coords[:-1]],
             "holes": [[list(map(lambda v: round(v, 4), c)) for c in r.coords[:-1]] for r in pg.interiors]}
            for pg in polys]


# ---- fit check --------------------------------------------------------------------------------
def fit_check(geo):
    """Internal parts vs. PCB underside: back-side bodies and THT leads."""
    errors = []
    z_pcb = P["pcb_bottom_z"]
    lead_floor = z_pcb - P["lead_len"]
    back_bodies = [(c["ref"], box(*c["body"]), z_pcb - c["height"]) for c in geo["components"] if c["side"] == "B"]
    leads = unary_union([Point(*p["xy"]).buffer(0.8) for c in geo["components"] for p in c["pads"] if p["drill"] > 0])

    bx, by = P["battery_xy"]
    bw, bh, bz = P["battery"]
    items = [("battery", box(bx, by, bx + bw, by + bh), P["tray_floor"] + bz),
             ("speaker", Point(*P["speaker_xy"]).buffer(P["speaker_d"] / 2 + 1.6), P["tray_floor"] + P["speaker_h"])]
    items += [(f"pillar{i}", Point(*xy).buffer(3.0), z_pcb) for i, xy in enumerate(P["support_pillars"])]
    items += [(f"boss_{h['ref']}", Point(*h["xy"]).buffer(P["boss_d"] / 2), z_pcb) for h in geo["holes"]]

    for name, shape, top in items:
        for ref, body, bottom in back_bodies:
            if shape.intersects(body) and top > bottom:
                errors.append(f"{name} collides with back-side {ref}")
        if name.startswith(("pillar", "boss")):
            if shape.intersects(leads):
                errors.append(f"{name} touches THT leads")
        elif top > lead_floor - 1.0:
            errors.append(f"{name} top z={top} leaves < 1 mm below the leads (z={lead_floor})")
    inside = rounded_rect(BOARD_W, BOARD_H, CORNER_R, -1.0)
    spk_ring = Point(*P["speaker_xy"]).buffer(P["speaker_d"] / 2 + 2.3)
    for i, xy in enumerate(P["support_pillars"]):
        if Point(*xy).buffer(3.0 + 1.0).intersects(spk_ring):
            errors.append(f"pillar{i} is within 1 mm of the speaker ring")
    for name, shape, _ in items:
        if not name.startswith("boss") and not inside.contains(shape):   # bosses merge into the wall
            errors.append(f"{name} extends outside the board footprint")
    return errors


# ---- solid meshes (Blender coordinates: x right, y up = -board y, z up; 1 unit = 1 mm) -----------
def to_blender(poly):
    from shapely.affinity import scale
    from shapely.geometry.polygon import orient
    flipped = scale(poly, xfact=1, yfact=-1, origin=(0, 0))
    parts = [flipped] if flipped.geom_type == "Polygon" else list(flipped.geoms)
    return [orient(p, sign=1.0) for p in parts if p.area > 1e-6]


def prism(poly, z0, z1):
    """Closed manifold prism of a (multi)polygon with holes -> (verts, faces)."""
    import shapely
    verts, faces = [], []
    for pg in to_blender(poly):
        index = {}
        rings = [list(pg.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in pg.interiors]
        base = len(verts)
        for ring in rings:
            for x, y in ring:
                index[(round(x, 6), round(y, 6))] = len(verts) - base
                verts.append((x, y, z0))
        n = len(verts) - base
        verts += [(x, y, z1) for x, y, _ in verts[base:base + n]]
        start = 0
        for ring in rings:
            m = len(ring)
            for i in range(m):
                a, b = base + start + i, base + start + (i + 1) % m
                faces.append((a, b, b + n, a + n))
            start += m
        for tri in shapely.constrained_delaunay_triangles(pg).geoms:
            ids = [index[(round(x, 6), round(y, 6))] for x, y in list(tri.exterior.coords)[:3]]
            (x0, y0), (x1, y1), (x2, y2) = [verts[base + i][:2] for i in ids]
            if (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0) < 0:
                ids.reverse()
            faces.append(tuple(base + n + i for i in ids))            # top, CCW from +z
            faces.append(tuple(base + i for i in reversed(ids)))      # bottom
    return verts, faces


def mesh_of(slabs):
    """Union of extruded slabs as one guaranteed-manifold mesh (manifold3d)."""
    import manifold3d as m3
    solid = None
    for poly, z0, z1 in slabs:
        contours = []
        for pg in to_blender(poly):
            contours.append([list(c) for c in pg.exterior.coords[:-1]])
            contours += [[list(c) for c in r.coords[:-1]] for r in pg.interiors]
        part = m3.CrossSection(contours, m3.FillRule.EvenOdd).extrude(z1 - z0).translate([0, 0, z0])
        solid = part if solid is None else solid + part
    if solid.status() != m3.Error.NoError:
        raise RuntimeError(f"manifold error {solid.status()}")
    m = solid.to_mesh()
    return {"verts": [[round(float(c), 5) for c in v[:3]] for v in m.vert_properties],
            "faces": [[int(i) for i in t] for t in m.tri_verts], "volume_mm3": round(solid.volume(), 1)}


def write_stl(mesh, path):
    import struct
    path.parent.mkdir(parents=True, exist_ok=True)
    v = mesh["verts"]
    with open(path, "wb") as fh:
        fh.write(b"StyloSynth-555".ljust(80, b" "))
        fh.write(struct.pack("<I", len(mesh["faces"])))
        for a, b, c in mesh["faces"]:
            pa, pb, pc = v[a], v[b], v[c]
            u = [pb[i] - pa[i] for i in range(3)]
            w = [pc[i] - pa[i] for i in range(3)]
            n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
            ln = math.sqrt(sum(x * x for x in n)) or 1.0
            fh.write(struct.pack("<12fH", *[x / ln for x in n], *pa, *pb, *pc, 0))


def grille_holes(center, radius, hole_d=3.0, pitch=4.2):
    sx, sy = center
    holes = []
    for j in range(-12, 13):
        for i in range(-12, 13):
            x, y = sx + (i + (j % 2) * 0.5) * pitch, sy + j * pitch * math.sqrt(3) / 2
            if math.hypot(x - sx, y - sy) <= radius:
                holes.append(Point(x, y).buffer(hole_d / 2, quad_segs=8))
    return unary_union(holes)


def tray_slabs(geo):
    """3D-printed tray as stacked 2.5D slabs (board coordinates, z from the tray bottom)."""
    c, w, fl = P["pcb_clear"], P["tray_wall"], P["tray_floor"]
    zb, zt = P["pcb_bottom_z"], P["pcb_bottom_z"] + P["pcb_t"]
    outer = rounded_rect(BOARD_W, BOARD_H, CORNER_R, c + w)
    cavity = rounded_rect(BOARD_W, BOARD_H, CORNER_R, c)
    wall = outer.difference(cavity)
    grille = grille_holes(P["speaker_xy"], P["speaker_d"] / 2 - 3.5)
    fi = P["feet_inset"] - c - w
    feet = unary_union([Point(x, y).buffer(P["feet_d"] / 2, quad_segs=16) for x, y in
                        [(fi, fi), (BOARD_W - fi, fi), (fi, BOARD_H - fi), (BOARD_W - fi, BOARD_H - fi)]])
    bosses = unary_union([Point(*h["xy"]).buffer(P["boss_d"] / 2, quad_segs=24) for h in geo["holes"]]).intersection(outer)
    inserts = unary_union([Point(*h["xy"]).buffer(P["insert_d"] / 2, quad_segs=24) for h in geo["holes"]])
    pillars = unary_union([Point(*xy).buffer(3.0, quad_segs=24) for xy in P["support_pillars"]])
    spk = Point(*P["speaker_xy"]).buffer(P["speaker_d"] / 2 + 2.3, quad_segs=48).difference(
        Point(*P["speaker_xy"]).buffer(P["speaker_d"] / 2 + 0.5, quad_segs=48))
    bx, by = P["battery_xy"]
    bw, bh, _ = P["battery"]
    g, t, L = 0.6, 1.6, 9.0                       # clearance, rib thickness, corner rib length
    ribs = unary_union([box(bx - g - t, by - g - t, bx - g, by - g + L), box(bx - g - t, by - g - t, bx - g + L, by - g),
                        box(bx + bw + g, by - g - t, bx + bw + g + t, by - g + L),
                        box(bx + bw + g - L, by - g - t, bx + bw + g + t, by - g),
                        box(bx - g - t, by + bh + g - L, bx - g, by + bh + g + t),
                        box(bx - g - t, by + bh + g, bx - g + L, by + bh + g + t),
                        box(bx + bw + g, by + bh + g - L, bx + bw + g + t, by + bh + g + t),
                        box(bx + bw + g - L, by + bh + g, bx + bw + g + t, by + bh + g + t)])
    z_ins = zb - P["insert_depth"]
    return [
        (outer.difference(feet).difference(grille), 0.0, 1.0),
        (outer.difference(grille), 1.0, fl),
        (unary_union([wall, bosses, pillars, spk, ribs]), fl, fl + 4.0),
        (unary_union([wall, bosses, pillars, ribs]), fl + 4.0, fl + 9.0),
        (unary_union([wall, bosses, pillars]), fl + 9.0, z_ins),
        (unary_union([wall, bosses.difference(inserts), pillars]), z_ins, zb),
        (wall, zb, zt),
    ]


def stylus_slabs():
    """Printable stylus body: tube with a cable channel and a tapered tip socket for a 4 mm brass tip."""
    d, L = P["stylus_d"], P["stylus_len"]
    slabs = [(Point(0, 0).buffer(d / 2, quad_segs=32).difference(Point(0, 0).buffer(2.0, quad_segs=16)), 0.0, L - 14)]
    for i in range(10):                                    # 14 mm taper from d to 5.6 mm
        r = d / 2 - (d / 2 - 2.8) * (i + 1) / 10
        slabs.append((Point(0, 0).buffer(r, quad_segs=32).difference(Point(0, 0).buffer(2.05, quad_segs=16)),
                      L - 14 + i * 1.4, L - 14 + (i + 1) * 1.4))
    return slabs


def acrylic_fit_check(geo):
    errors = []
    z_leads = P["acr_t"] + P["acr_standoff"] - P["lead_len"]
    bat_top = P["acr_t"] + P["battery"][2]
    if bat_top > z_leads - 1.0:
        errors.append(f"acrylic: battery top {bat_top} too close to leads {z_leads}")
    ring_top = P["acr_t"] * (1 + P["acr_rings"])
    if ring_top > P["acr_t"] + P["acr_standoff"]:
        errors.append("acrylic: ring stack is taller than the standoffs")
    return errors


def main():
    board = pcbnew.LoadBoard(str(PCB))
    geo = extract_pcb(board)
    (OUT / "textures").mkdir(parents=True, exist_ok=True)
    (OUT / "acrylic").mkdir(parents=True, exist_ok=True)
    (OUT / "pcb_geometry.json").write_text(json.dumps(geo, indent=1))

    compose_texture("F").save(OUT / "textures" / "pcb_top.png")
    compose_texture("B").save(OUT / "textures" / "pcb_bottom.png")

    layers, bolts = acrylic_layers(geo)
    acr = {}
    for name, (poly, qty) in layers.items():
        write_dxf(poly, OUT / "acrylic" / f"{name}_x{qty}.dxf")
        acr[name] = {"qty": qty, "rings": poly_rings(poly)}
    (OUT / "enclosure.json").write_text(json.dumps({"params": P, "acrylic": acr, "acrylic_bolts": bolts}, indent=1))

    meshes = {"tray": mesh_of(tray_slabs(geo)), "stylus": mesh_of(stylus_slabs()),
              "acrylic": {name: mesh_of([(poly, 0.0, P["acr_t"])]) for name, (poly, _q) in layers.items()},
              "pcb": mesh_of([(rounded_rect(BOARD_W, BOARD_H, CORNER_R).difference(
                  unary_union([Point(*h["xy"]).buffer(h["d"] / 2, quad_segs=24) for h in geo["holes"]])),
                  0.0, P["pcb_t"])])}
    (OUT / "meshes.json").write_text(json.dumps(meshes))
    write_stl(meshes["tray"], OUT / "print" / "tray.stl")
    write_stl(meshes["stylus"], OUT / "print" / "stylus_body.stl")
    print(f"tray {meshes['tray']['volume_mm3'] / 1000:.1f} cm3, stylus {meshes['stylus']['volume_mm3'] / 1000:.1f} cm3 "
          "(manifold) -> out/print/*.stl")

    errors = fit_check(geo) + acrylic_fit_check(geo)
    print(f"{len(geo['components'])} components, {len(geo['holes'])} holes; textures + "
          f"{len(layers)} DXFs written to {OUT}")
    if errors:
        print("FIT CHECK FAILED:\n  " + "\n  ".join(errors))
        return 1
    print("fit check: PASS (battery, speaker, bosses, pillars clear of back-side parts and leads)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
