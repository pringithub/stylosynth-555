#!/usr/bin/env bash
# Export the JLCPCB/PCBWay fabrication package, 3D model, schematic PDF and renders (KiCad 7 kicad-cli).
set -euo pipefail
cd "$(dirname "$0")/.."
PCB=kicad/stylosynth.kicad_pcb
SCH=kicad/stylosynth.kicad_sch
OUT=fab
rm -rf "$OUT" && mkdir -p "$OUT/gerbers" ../docs/renders

kicad-cli pcb export gerbers -o "$OUT/gerbers/" \
  --layers F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts \
  --subtract-soldermask --use-drill-file-origin "$PCB"
kicad-cli pcb export drill -o "$OUT/gerbers/" --format excellon --excellon-separate-th \
  --excellon-units mm --generate-map --map-format gerberx2 "$PCB"
kicad-cli pcb export pos -o "$OUT/stylosynth-pos.csv" --format csv --units mm --side both "$PCB"
kicad-cli pcb export step -o "$OUT/stylosynth.step" --subst-models --force "$PCB" || \
  echo "warning: STEP export failed (3D models missing?)"
kicad-cli sch export pdf -o "$OUT/stylosynth-schematic.pdf" "$SCH"
kicad-cli pcb export pdf -o "$OUT/stylosynth-top.pdf" --layers F.Cu,F.SilkS,F.Mask,Edge.Cuts "$PCB"
kicad-cli pcb export pdf -o "$OUT/stylosynth-bottom.pdf" --layers B.Cu,B.SilkS,Edge.Cuts --mirror "$PCB"

(cd "$OUT/gerbers" && zip -q ../stylosynth-gerbers.zip ./*)
cp ../bom/bom.csv "$OUT/"

for side in top bottom; do
  pdftoppm -png -r 150 -singlefile "$OUT/stylosynth-$side.pdf" "../docs/renders/pcb-$side"
done
pdftoppm -png -r 60 -singlefile "$OUT/stylosynth-schematic.pdf" ../docs/renders/schematic

echo "fab package:"; ls -1 "$OUT"
