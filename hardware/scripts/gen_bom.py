#!/usr/bin/env python3
"""Generate bom/bom.csv and bom/bom.md from circuit.py plus off-board items.

MPNs marked verify=yes are typical/example parts: check stock and exact dimensions before ordering.
Prices are rough single-unit estimates in USD and only indicate magnitude.
"""
import csv
import re
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import circuit  # noqa: E402

OUT = circuit.HW.parent / "bom"

# (value, footprint-substring) -> (manufacturer, mpn, est_unit_usd, verify)
SOURCING = [
    (("TLC555", ""), ("Texas Instruments", "TLC555CP", 1.10, "no")),
    (("CD4040", ""), ("Texas Instruments", "CD4040BE", 0.70, "no")),
    (("LM358", ""), ("Texas Instruments", "LM358P", 0.45, "no")),
    (("LM386", ""), ("Texas Instruments", "LM386N-1/NOPB", 1.20, "no")),
    (("LP2950-5.0", ""), ("Texas Instruments", "LP2950ACZ-5.0/NOPB", 1.00, "no")),
    (("1N5819", ""), ("onsemi / Vishay", "1N5819", 0.20, "no")),
    (("PWR", "LED"), ("Kingbright", "WP710A10ID (3 mm red diffused)", 0.25, "yes")),
    (("POWER", "JS2020"), ("C&K", "JS202011CQN", 0.60, "no")),
    (("OCT -1", "JS2020"), ("C&K", "JS202011CQN", 0.60, "no")),
    (("OCT -2", "JS2020"), ("C&K", "JS202011CQN", 0.60, "no")),
    (("TONE", "JS2020"), ("C&K", "JS202011CQN", 0.60, "no")),
    (("VIBRATO", "JS2020"), ("C&K", "JS202011CQN", 0.60, "no")),
    (("STYLUS", "SJ1-3535"), ("Same Sky (CUI)", "SJ1-3535NG", 1.30, "no")),
    (("PHONES", "SJ1-3535"), ("Same Sky (CUI)", "SJ1-3535NG", 1.30, "no")),
    (("9V DC (centre -)", ""), ("Same Sky (CUI)", "PJ-102AH (5.5x2.1 mm)", 0.90, "yes")),
    (("", "JST_XH"), ("JST", "B2B-XH-A(LF)(SN)", 0.15, "no")),
    (("A10k", ""), ("Alps Alpine / generic", "RK09K series 9 mm vertical, 10k log (A10K), 15 mm shaft", 1.50, "yes")),
    (("B10k", ""), ("Alps Alpine / generic", "RK09K series 9 mm vertical, 10k lin (B10K), 15 mm shaft", 1.50, "yes")),
    (("1k", "3296W"), ("Bourns", "3296W-1-102LF", 1.60, "no")),
    (("2k", "3296W"), ("Bourns", "3296W-1-202LF", 1.60, "no")),
    (("100k", "3296W"), ("Bourns", "3296W-1-104LF", 1.60, "no")),
    (("22n", "C_Rect"), ("WIMA", "MKP2 22nF 100V 2.5% 5 mm (polypropylene)", 0.60, "yes")),
    (("47n", "C_Rect"), ("WIMA", "MKS2 47nF 63V 5 mm", 0.35, "yes")),
    (("100n", "C_Rect"), ("WIMA", "MKS2 100nF 63V 5 mm", 0.35, "yes")),
    (("1u", "C_Rect"), ("WIMA", "MKS2 1uF 63V 5 mm", 0.60, "yes")),
    (("100n", "C_Disc"), ("KEMET", "C322C104K5R5TA", 0.25, "yes")),
    (("10n", "C_Disc"), ("KEMET", "C322C103K5R5TA", 0.25, "yes")),
    (("47n", "C_Disc"), ("KEMET", "C322C473K5R5TA", 0.25, "yes")),
    (("220u", ""), ("Panasonic", "EEU-FC1C221 (220uF 16V, 8 mm, 3.5 mm pitch)", 0.45, "yes")),
    (("100u", ""), ("Panasonic", "EEU-FC1C101 (100uF 16V, 6.3 mm, 2.5 mm pitch)", 0.35, "yes")),
    (("47u", ""), ("Panasonic", "47uF 16V, 5 mm dia, 2 mm pitch (FC/FR series)", 0.30, "yes")),
    (("22u", ""), ("Panasonic", "EEU-FC1E220 (22uF 25V, 5 mm, 2 mm pitch)", 0.30, "yes")),
    (("10u", ""), ("Panasonic", "EEU-FC1E100 (10uF 25V, 5 mm, 2 mm pitch)", 0.25, "yes")),
]

OFF_BOARD = [  # (qty, description, manufacturer, mpn, est_unit_usd, verify)
    (3, "IC socket DIP-8 (U2, U4, U5)", "generic", "DIP-8 machined socket", 0.30, "yes"),
    (1, "IC socket DIP-16 (U3)", "generic", "DIP-16 machined socket", 0.40, "yes"),
    (1, "Speaker 8 ohm 0.5-1 W, 40-50 mm", "generic", "8R 1W 50 mm", 2.50, "yes"),
    (1, "9V battery snap with leads", "generic", "9V snap, 150 mm leads", 0.40, "yes"),
    (4, "JST XH 2-pin housing + 2 crimp contacts (battery, speaker)", "JST", "XHP-2 + SXH-001T-P0.6", 0.20, "no"),
    (1, "Stylus: 3.5 mm mono plug + 1 m coiled/flex cable", "generic", "3.5 mm mono plug + cable", 2.00, "yes"),
    (1, "Stylus tip: 4 mm banana plug or M3 brass screw/insert", "generic", "brass tip", 0.50, "yes"),
    (2, "Knob for 6 mm shaft (volume, depth)", "generic", "6 mm knob", 0.80, "yes"),
    (4, "Printed tray: M3 heat-set insert, M3 x 5.7 mm (4.0 mm hole)", "generic", "Ruthex-style M3x5.7", 0.15, "yes"),
    (4, "Printed tray: M3 x 6 mm screw, pan/button head (PCB to tray)", "generic", "ISO 7380 M3x6", 0.05, "no"),
    (4, "Acrylic: M3 x 25 mm brass hex standoff, female-female", "generic", "M3x25 F-F standoff", 0.25, "yes"),
    (8, "Acrylic: M3 x 6 mm screw (standoffs to PCB and bottom plate)", "generic", "ISO 7380 M3x6", 0.05, "no"),
    (4, "Acrylic: M3 x 30 mm screw + M3 nut (clamps the ring stack)", "generic", "ISO 7380 M3x30 + DIN 934", 0.10,
     "no"),
    (1, "Acrylic: 3 mm clear cast acrylic, laser cut (1 bottom plate + 8 rings, 151 x 113 mm)", "Ponoko/local laser",
     "see enclosure/out/acrylic/*.dxf", 15.00, "yes"),
    (4, "Rubber foot, adhesive", "generic", "10 mm bumpon", 0.10, "yes"),
    (1, "PCB 200x120 mm, 2-layer, 1.6 mm, ENIG, black mask/white silk (price per board of 5)", "JLCPCB/PCBWay",
     "fab order", 12.00, "yes"),
]


def natural_key(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def source_for(part):
    for (val, fp), src in SOURCING:
        if (not val or val == part.value) and (not fp or fp in part.footprint):
            return src
    return None


def main():
    groups = OrderedDict()
    for p in sorted(circuit.PARTS, key=lambda p: natural_key(p.ref)):
        if p.ref.startswith(("H", "K")):
            continue
        key = (p.value, p.footprint)
        groups.setdefault(key, []).append(p)

    rows, missing = [], []
    for (value, fp), parts in groups.items():
        p0 = parts[0]
        src = source_for(p0)
        if src is None:
            if p0.lib_id == "Device:R":
                src = ("Yageo / generic", f"{value} metal film 1% 0.25 W (e.g. Yageo MFR-25 series)", 0.03, "no")
            else:
                missing.append(p0.ref)
                src = ("?", "?", 0.0, "yes")
        manu, mpn, price, verify = src
        refs = ", ".join(p.ref for p in parts)
        rows.append([len(parts), refs, value, p0.desc, fp.split(":")[1], manu, mpn, verify, f"{price:.2f}",
                     f"{price * len(parts):.2f}"])
    for qty, desc, manu, mpn, price, verify in OFF_BOARD:
        rows.append([qty, "-", "-", desc, "-", manu, mpn, verify, f"{price:.2f}", f"{price * qty:.2f}"])
    if missing:
        raise SystemExit(f"no sourcing for: {missing}")

    header = ["Qty", "References", "Value", "Description", "Footprint", "Manufacturer", "MPN", "Verify",
              "Est. unit USD", "Est. line USD"]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)

    total = sum(float(r[9]) for r in rows)
    n_parts = sum(r[0] for r in rows if r[1] != "-")
    md = ["# StyloSynth-555 BOM", "",
          "Generated by `hardware/scripts/gen_bom.py` from `circuit.py`. Do not edit by hand.", "",
          f"- On-board parts: **{n_parts}** in **{len(groups)}** line items. Off-board items are listed at the end.",
          f"- Rough cost for one unit (parts plus 1/5 of a 5-board PCB order): **~${total:.0f} USD**. "
          "Prices are indicative only.",
          "- **Verify = yes**: the MPN is a typical example. Confirm stock, lead pitch/diameter and shaft "
          "style before ordering.",
          "- Order the PCB with an **ENIG** finish, because the key pads are exposed copper.",
          "- Search: [Mouser](https://www.mouser.com/) · [DigiKey](https://www.digikey.com/) · "
          "[LCSC](https://www.lcsc.com/)", "",
          "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        md.append("| " + " | ".join(str(c).replace("|", "/") for c in r) + " |")
    md += ["", f"**Estimated total: ${total:.2f}**", ""]
    (OUT / "bom.md").write_text("\n".join(md))
    print(f"{len(rows)} BOM lines, {n_parts} on-board parts, est. ${total:.2f} -> {OUT.relative_to(circuit.HW.parent)}")


if __name__ == "__main__":
    main()
