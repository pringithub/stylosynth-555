#!/usr/bin/env python3
"""Export the netlist from the generated schematic with kicad-cli and compare it to circuit.py.

This stands in for ERC on KiCad 7: it proves the drawn schematic has exactly the intended
connectivity (every pin on the right net, no extra or missing connections).
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circuit  # noqa: E402
from sexpr import find, find1, parse  # noqa: E402

KICAD = circuit.HW / "kicad"
SCH = KICAD / "stylosynth.kicad_sch"
NET = KICAD / "stylosynth.net"


def exported_nets():
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", str(NET), str(SCH)], check=True,
                   capture_output=True)
    root = parse(NET.read_text())
    nets = {}
    for n in find(find1(root, "nets"), "net"):
        name = find1(n, "name")[1].lstrip("/")
        nodes = {(find1(x, "ref")[1], find1(x, "pin")[1]) for x in find(n, "node")}
        nodes = {nd for nd in nodes if not nd[0].startswith("#")}
        if name.startswith("unconnected-") or name.startswith("Net-("):
            if len(nodes) > 1:
                nets[name] = nodes
            continue
        nets[name] = nodes
    comps = {find1(c, "ref")[1]: (find1(c, "value")[1], find1(c, "footprint")[1] if find1(c, "footprint") else "")
             for c in find(find1(root, "components"), "comp")}
    return nets, comps


def main():
    got, comps = exported_nets()
    want = {k: set(v) for k, v in circuit.nets().items()}
    errors = []
    for name in sorted(set(want) | set(got)):
        if want.get(name) != got.get(name):
            errors.append(f"net {name}: expected {sorted(want.get(name, []))} got {sorted(got.get(name, []))}")
    for p in circuit.PARTS:
        if p.ref not in comps:
            errors.append(f"missing component {p.ref}")
        elif comps[p.ref] != (p.value, p.footprint):
            errors.append(f"{p.ref}: expected {(p.value, p.footprint)} got {comps[p.ref]}")
    if errors:
        print("\n".join(errors))
        raise SystemExit(f"FAIL: {len(errors)} mismatches")
    print(f"PASS: {len(want)} nets and {len(circuit.PARTS)} components match circuit.py")


if __name__ == "__main__":
    main()
