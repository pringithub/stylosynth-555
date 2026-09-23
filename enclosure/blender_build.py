"""Build the StyloSynth-555 PCB assembly and both enclosures in Blender (tested on 3.3).

Run inside Blender (e.g. via the MCP bridge or the Text editor):
    exec(open("/path/to/enclosure/blender_build.py").read())
Inputs: enclosure/out/{pcb_geometry,enclosure,meshes}.json and textures/ (from gen_geometry.py).
Outputs: enclosure/out/print/*.stl, enclosure/out/stylosynth_enclosures.blend
Scene units: 1 Blender unit = 1 mm. Board top-left is at the origin, +x right, -y towards the player.
"""
import json
import math
import struct
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ENC = Path(globals().get("ENCLOSURE_DIR", "/home/pring5/Projects/Personal/Active/pcb_synthesizer/enclosure"))
OUT = ENC / "out"
GEO = json.loads((OUT / "pcb_geometry.json").read_text())
CFG = json.loads((OUT / "enclosure.json").read_text())
MESHES = json.loads((OUT / "meshes.json").read_text())
P = CFG["params"]
BW, BH, PCB_T = GEO["board"]["w"], GEO["board"]["h"], GEO["board"]["t"]
ACRYLIC_DX = BW + 40.0                       # acrylic version is placed to the right of the printed one
COLLS = ["SS_PCB_Assembly", "SS_Printed", "SS_Acrylic"]


# ---- scene helpers ----------------------------------------------------------------------------
def reset_scene():
    for name in COLLS:
        coll = bpy.data.collections.get(name)
        if coll:
            for ob in list(coll.all_objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.collections.remove(coll)
    for ob in [o for o in bpy.data.objects if o.name.startswith("SS_")]:
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(m)
    us = bpy.context.scene.unit_settings
    us.system, us.scale_length, us.length_unit = "METRIC", 0.001, "MILLIMETERS"
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type == "VIEW_3D":
            area.spaces.active.clip_start, area.spaces.active.clip_end = 0.1, 20000
    colls = {}
    for name in COLLS:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        colls[name] = c
    return colls


def socket(node, ident):
    return next(s for s in node.inputs if s.identifier == ident)


MATS = {}


def material(name, color, metallic=0.0, rough=0.5, alpha=1.0, transmission=0.0, image=None):
    key = f"SS_{name}"
    if key in MATS:
        return MATS[key]
    mat = bpy.data.materials.get(key) or bpy.data.materials.new(key)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    socket(bsdf, "Base Color").default_value = (*color, 1.0)
    socket(bsdf, "Metallic").default_value = metallic
    socket(bsdf, "Roughness").default_value = rough
    socket(bsdf, "Alpha").default_value = alpha
    if transmission:
        socket(bsdf, "Transmission").default_value = transmission
        socket(bsdf, "IOR").default_value = 1.49
    if alpha < 1.0:
        mat.blend_method = "BLEND"
        mat.show_transparent_back = False
    if image:
        tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None) or nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(image), check_existing=True)
        tex.image.reload()
        nt.links.new(tex.outputs["Color"], socket(bsdf, "Base Color"))
    mat.diffuse_color = (*color, alpha)
    MATS[key] = mat
    return mat


def mesh_object(name, verts, faces, coll, mat=None, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    coll.objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def bm_object(name, bm, coll, mat, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    coll.objects.link(ob)
    me.materials.append(mat)
    return ob


def bx(name, x0, y0, x1, y1, z0, z1, mat, coll):
    """Axis-aligned box from board coordinates (y down) and z range."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * abs(x1 - x0), -(y0 + y1) / 2 + v.co.y * abs(y1 - y0),
                       (z0 + z1) / 2 + v.co.z * abs(z1 - z0)))
    return bm_object(name, bm, coll, mat)


def cyl(name, cx, cy, r, z0, z1, mat, coll, segs=32, r_top=None, axis="z"):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r_top is None else r_top, depth=abs(z1 - z0))
    for v in bm.verts:
        if axis == "y":                       # lay the cylinder along board -y (towards the rear edge)
            v.co = Vector((v.co.x, v.co.z, v.co.y))
    for v in bm.verts:
        v.co += Vector((cx, -cy, (z0 + z1) / 2)) if axis == "z" else Vector((cx, -cy, 0))
    return bm_object(name, bm, coll, mat)


def boolean_union(name, parts, coll, mat):
    base = parts[0]
    for other in parts[1:]:
        mod = base.modifiers.new(f"U_{other.name}", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "UNION", "EXACT", other
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    for ob in parts:
        bpy.data.objects.remove(ob, do_unlink=True)
    me.name = name
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    me.materials.clear()
    me.materials.append(mat)
    return ob


def non_manifold_edges(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    bm.free()
    return n


def write_stl(ob, path, rotate_x_deg=0.0):
    me = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    me.calc_loop_triangles()
    rot = math.radians(rotate_x_deg)
    c, s = math.cos(rot), math.sin(rot)

    def tf(v):
        x, y, z = v
        return (x, y * c - z * s, y * s + z * c)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"StyloSynth-555".ljust(80, b" "))
        fh.write(struct.pack("<I", len(me.loop_triangles)))
        for tri in me.loop_triangles:
            pts = [tf(me.vertices[i].co) for i in tri.vertices]
            n = tf(tri.normal)
            fh.write(struct.pack("<12fH", *n, *pts[0], *pts[1], *pts[2], 0))
    ob.to_mesh_clear()


# ---- PCB assembly -------------------------------------------------------------------------------
def build_pcb(coll):
    m = MESHES["pcb"]
    ob = mesh_object("SS_PCB", m["verts"], m["faces"], coll)
    me = ob.data
    top = material("PCB_top", (0.1, 0.1, 0.1), rough=0.35, image=OUT / "textures" / "pcb_top.png")
    bot = material("PCB_bottom", (0.1, 0.1, 0.1), rough=0.35, image=OUT / "textures" / "pcb_bottom.png")
    edge = material("FR4_edge", (0.05, 0.05, 0.05), rough=0.6)
    for mt in (top, bot, edge):
        me.materials.append(mt)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        poly.material_index = 0 if poly.normal.z > 0.5 else 1 if poly.normal.z < -0.5 else 2
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (co.x / BW, 1.0 + co.y / BH)

    mats = {
        "ic": material("IC", (0.02, 0.02, 0.02), rough=0.4), "socket": material("Socket", (0.08, 0.08, 0.08)),
        "res": material("Resistor", (0.35, 0.55, 0.85), rough=0.5), "lead": material("Lead", (0.8, 0.8, 0.8), 1.0, 0.3),
        "disc": material("Ceramic", (0.85, 0.55, 0.1)), "film": material("Film", (0.75, 0.08, 0.06), rough=0.4),
        "ecap": material("Electrolytic", (0.05, 0.1, 0.35), rough=0.4), "alu": material("Alu", (0.8, 0.8, 0.82), 1.0, 0.3),
        "trim": material("Trimmer", (0.1, 0.25, 0.75)), "brass": material("Brass", (0.8, 0.6, 0.25), 1.0, 0.3),
        "led": material("LED", (0.9, 0.05, 0.05), rough=0.2), "white": material("JST", (0.92, 0.9, 0.85)),
        "knob": material("Knob", (0.03, 0.03, 0.03), rough=0.3), "steel": material("Steel", (0.7, 0.7, 0.72), 1.0, 0.35),
    }
    count = 0
    for c in GEO["components"]:
        fp, ref, h = c["fpid"], c["ref"], c["height"]
        if "KEYPAD" in fp:
            continue
        x0, y0, x1, y1 = c["body"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        side = 1 if c["side"] == "F" else -1
        zb = PCB_T if side > 0 else 0.0

        def z(a, b):
            return (zb + side * a, zb + side * b) if side > 0 else (zb + side * b, zb + side * a)
        n = f"SS_{ref}"
        pads = c["pads"]
        if "DIP-" in fp:
            bx(n + "_socket", x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3, *z(0, 3.0), mats["socket"], coll)
            px = sorted({round(p["xy"][0], 2) for p in pads})
            bx(n, px[0] + 1.0, y0 + 0.6, px[-1] - 1.0, y1 - 0.6, *z(3.0, 6.5), mats["ic"], coll)
        elif "R_Axial" in fp:
            p1, p2 = pads[0]["xy"], pads[1]["xy"]
            cyl(n, *p1, 1.25, *z(0.6, 7.0), mats["res"], coll, 16)
            cyl(n + "_lead", *p2, 0.3, *z(0, 8.0), mats["lead"], coll, 8)
        elif "C_Disc" in fp:
            wide = (x1 - x0) >= (y1 - y0)
            bx(n, x0 + 0.5, cy - 1.2, x1 - 0.5, cy + 1.2, *z(1.0, h), mats["disc"], coll) if wide else \
                bx(n, cx - 1.2, y0 + 0.5, cx + 1.2, y1 - 0.5, *z(1.0, h), mats["disc"], coll)
        elif "C_Rect" in fp:
            bx(n, x0, y0, x1, y1, *z(0, h), mats["film"], coll)
        elif "CP_Radial" in fp:
            r = 4.0 if "D8.0" in fp else 3.15 if "D6.3" in fp else 2.5
            cyl(n, cx, cy, r, *z(0.3, h - 0.4), mats["ecap"], coll, 32)
            cyl(n + "_top", cx, cy, r - 0.3, *z(h - 0.4, h), mats["alu"], coll, 32)
        elif "TO-92" in fp:
            bx(n, x0 + 0.3, y0 + 1.0, x1 - 0.3, y1 - 0.8, *z(2.0, h), mats["ic"], coll)
        elif "LED_D3" in fp:
            cyl(n, cx, cy, 1.5, *z(0, 3.5), mats["led"], coll, 24)
            cyl(n + "_dome", cx, cy, 1.5, *z(3.5, 5.3), mats["led"], coll, 24, r_top=0.4)
        elif "DO-41" in fp:
            cyl(n, cx, cy, min(x1 - x0, y1 - y0) / 2, *z(0.5, 5.7), mats["ic"], coll, 16)
        elif "3296W" in fp:
            bx(n, x0, y0, x1, y1, *z(0, 9.5), mats["trim"], coll)
            cyl(n + "_screw", x0 + 1.4, y0 + 1.4, 1.1, *z(9.5, 10.3), mats["brass"], coll, 12) \
                if (x1 - x0) > (y1 - y0) else cyl(n + "_screw", x0 + 1.4, y1 - 1.4, 1.1, *z(9.5, 10.3),
                                                  mats["brass"], coll, 12)
        elif "RK09K" in fp:
            bx(n, x0, y0, x1, y1, *z(0, 6.5), mats["steel"], coll)
            cyl(n + "_shaft", cx, cy, 3.0, *z(6.5, 17.0), mats["alu"], coll, 24)
            cyl(n + "_knob", cx, cy, 7.5, *z(9.0, 21.0), mats["knob"], coll, 48, r_top=6.8)
            bx(n + "_mark", cx - 0.5, cy - 6.5, cx + 0.5, cy - 3.0, *z(21.0, 21.2), mats["alu"], coll)
        elif "JS202011" in fp:
            bx(n, x0 + 0.4, y0 + 0.6, x1 - 0.4, y1 - 0.6, *z(0, 3.8), mats["steel"], coll)
            bx(n + "_lever", cx - 2.5, cy - 0.8, cx - 0.5, cy + 0.8, *z(3.8, 7.5), mats["knob"], coll)
        elif "SJ1-3535" in fp:
            bx(n, x0 + 0.3, y0 + 3.0, x1 - 0.3, y1, *z(0, 5.0), mats["ic"], coll)
            cyl(n + "_nose", cx, 0.0, 3.0, 0, 0, mats["ic"], coll, 24, axis="y")
            nose = bpy.data.objects[n + "_nose"]
            for v in nose.data.vertices:
                v.co.y = -(y0 + 1.5) + (v.co.y * (3.0 / max(1e-6, 3.0)))
                v.co.z += zb + side * 2.8
        elif "PJ-102AH" in fp:
            bx(n, x0, y0, x1, y1, *z(0, 11.0), mats["ic"], coll)
        elif "JST_XH" in fp:
            bx(n, x0 + 0.2, y0 + 0.2, x1 - 0.2, y1 - 0.2, *z(0, 7.0), mats["white"], coll)
        else:
            bx(n, x0, y0, x1, y1, *z(0, h), mats["ic"], coll)
        count += 1
    for hole in GEO["holes"]:
        cyl(f"SS_screw_{hole['ref']}", *hole["xy"], 2.75, PCB_T, PCB_T + 2.0, mats["steel"], coll, 24)
    return count


# ---- enclosures -------------------------------------------------------------------------------
def slabs_object(name, slabs, coll, mat):
    parts = [mesh_object(f"{name}_part{i}", s["verts"], s["faces"], coll) for i, s in enumerate(slabs)]
    return boolean_union(name, parts, coll, mat)


def add_internals(coll, dx, z_floor):
    bat = material("Battery9V", (0.05, 0.05, 0.05), rough=0.4)
    gold = material("BatteryLabel", (0.85, 0.65, 0.1), 0.6, 0.35)
    spk = material("Speaker", (0.15, 0.15, 0.15), 0.3, 0.5)
    bxy, (bw, bh, bz) = P["battery_xy"], P["battery"]
    ob = bx("SS_battery" + ("_acr" if dx else ""), bxy[0], bxy[1], bxy[0] + bw, bxy[1] + bh, z_floor, z_floor + bz,
            bat, coll)
    ob.location.x = dx
    lb = bx("SS_battery_label" + ("_acr" if dx else ""), bxy[0] + 12, bxy[1] - 0.05, bxy[0] + bw - 4, bxy[1] + bh + 0.05,
            z_floor + 1, z_floor + bz - 1, gold, coll)
    lb.location.x = dx
    s = cyl("SS_speaker" + ("_acr" if dx else ""), *P["speaker_xy"], P["speaker_d"] / 2, z_floor, z_floor + P["speaker_h"],
            spk, coll, 64, r_top=P["speaker_d"] / 2 - 4)
    s.location.x = dx


def build_printed(coll, pcb_coll):
    petg = material("PETG_print", (0.13, 0.32, 0.55), rough=0.55)
    tray = slabs_object("SS_Tray", MESHES["tray_slabs"], coll, petg)
    stylus = slabs_object("SS_Stylus_body", MESHES["stylus_slabs"], coll, petg)
    tray_nm, stylus_nm = non_manifold_edges(tray), non_manifold_edges(stylus)
    write_stl(tray, OUT / "print" / "tray.stl")
    write_stl(stylus, OUT / "print" / "stylus_body.stl")
    # display the stylus lying beside the tray, tip towards the player
    stylus.rotation_euler = (math.radians(-90), 0, 0)
    stylus.location = (BW + 14.0, -BH + 5.0, P["stylus_d"] / 2)
    brass = MATS["SS_Brass"]
    tip = cyl("SS_Stylus_tip", 0, 0, 2.0, 0, 8, brass, coll, 24, r_top=1.2)
    tip.rotation_euler = (math.radians(-90), 0, 0)
    tip.location = (BW + 14.0, -BH + 5.0 - P["stylus_len"] - 2.0, P["stylus_d"] / 2)
    feet = material("Rubber", (0.02, 0.02, 0.02), rough=0.9)
    fi = P["feet_inset"] - P["pcb_clear"] - P["tray_wall"]
    for i, (x, y) in enumerate([(fi, fi), (BW - fi, fi), (fi, BH - fi), (BW - fi, BH - fi)]):
        cyl(f"SS_foot{i}", x, y, P["feet_d"] / 2 - 0.3, -2.0, 1.0, feet, coll, 24)
    add_internals(coll, 0.0, P["tray_floor"])
    inst = bpy.data.objects.new("SS_PCB_in_tray", None)
    inst.instance_type, inst.instance_collection = "COLLECTION", pcb_coll
    inst.location = (0, 0, P["pcb_bottom_z"])
    coll.objects.link(inst)
    return tray_nm, stylus_nm


def build_acrylic(coll, pcb_coll):
    clear = material("Acrylic_clear", (0.85, 0.93, 1.0), rough=0.05, alpha=0.28, transmission=1.0)
    t = P["acr_t"]
    bp = MESHES["acrylic"]["bottom_plate"]
    mesh_object("SS_Acr_bottom", bp["verts"], bp["faces"], coll, clear, loc=(ACRYLIC_DX, 0, 0))
    ring = MESHES["acrylic"]["ring"]
    for i in range(P["acr_rings"]):
        mesh_object(f"SS_Acr_ring{i + 1}", ring["verts"], ring["faces"], coll, clear, loc=(ACRYLIC_DX, 0, t * (i + 1)))
    steel = MATS["SS_Steel"]
    z_pcb = t + P["acr_standoff"]
    for h in GEO["holes"]:
        so = cyl(f"SS_standoff_{h['ref']}", *h["xy"], 3.17, t, z_pcb, material("Brass", (0.8, 0.6, 0.25), 1.0, 0.3),
                 coll, 6)
        so.location.x = ACRYLIC_DX
        sc = cyl(f"SS_acr_screw_{h['ref']}", *h["xy"], 2.75, -2.0, 0.0, steel, coll, 24)
        sc.location.x = ACRYLIC_DX
    ring_top = t * (1 + P["acr_rings"])
    for i, (x, y) in enumerate(CFG["acrylic_bolts"]):
        for nm, z0, z1, r in (("head", ring_top, ring_top + 2.0, 2.75), ("nut", -2.4, 0.0, 3.1)):
            o = cyl(f"SS_acr_bolt{i}_{nm}", x, y, r, z0, z1, steel, coll, 6 if nm == "nut" else 24)
            o.location.x = ACRYLIC_DX
    add_internals(coll, ACRYLIC_DX, t)
    inst = bpy.data.objects.new("SS_PCB_in_acrylic", None)
    inst.instance_type, inst.instance_collection = "COLLECTION", pcb_coll
    inst.location = (ACRYLIC_DX, 0, z_pcb)
    coll.objects.link(inst)


def setup_view_and_light():
    scn = bpy.context.scene
    scn.render.engine = scn.render.engine          # keep whatever engine the user has
    cam = bpy.data.objects.get("Camera")
    if cam:
        cam.data.clip_start, cam.data.clip_end, cam.data.lens = 1, 5000, 50
        cam.location = (ACRYLIC_DX / 2 + BW / 2, -BH - 380, 330)
        target = Vector((ACRYLIC_DX / 2 + BW / 2, -BH / 2, 10))
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        scn.camera = cam
    light = bpy.data.objects.get("Light")
    if light and light.type == "LIGHT":
        light.data.type, light.data.energy = "SUN", 4.0
        light.rotation_euler = (math.radians(40), math.radians(15), math.radians(30))
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type == "VIEW_3D":
            sp = area.spaces.active
            sp.shading.type = "MATERIAL"
            r3d = sp.region_3d
            r3d.view_location = Vector((ACRYLIC_DX / 2 + BW / 2, -BH / 2, 15))
            r3d.view_distance = 520
            from mathutils import Euler
            r3d.view_rotation = Euler((math.radians(55), 0, math.radians(0)), "XYZ").to_quaternion()


def main():
    colls = reset_scene()
    n = build_pcb(colls["SS_PCB_Assembly"])
    bpy.context.view_layer.layer_collection.children["SS_PCB_Assembly"].exclude = True
    tray_nm, stylus_nm = build_printed(colls["SS_Printed"], colls["SS_PCB_Assembly"])
    build_acrylic(colls["SS_Acrylic"], colls["SS_PCB_Assembly"])
    setup_view_and_light()
    blend = OUT / "stylosynth_enclosures.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
    print(f"components: {n}; tray non-manifold edges: {tray_nm}; stylus non-manifold edges: {stylus_nm}")
    print(f"saved {blend}")


main()
