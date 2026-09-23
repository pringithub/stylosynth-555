#!/usr/bin/env python3
"""Print pin tables for KiCad library symbols: dump_pins.py Lib:Name [...]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sexpr import load_lib_symbol, symbol_pins  # noqa: E402

SYMDIR = Path("/usr/share/kicad/symbols")

for full in sys.argv[1:]:
    lib, name = full.split(":")
    sym = load_lib_symbol(SYMDIR / f"{lib}.kicad_sym", name)
    print(f"== {full}")
    for u, num, nm, typ, x, y, a, ln in sorted(symbol_pins(sym), key=lambda p: (p[0], p[1])):
        print(f"  u{u} {num:>3} {nm:<10} {typ:<14} ({x:7.2f},{y:7.2f}) a={a:g} len={ln:g}")
