"""StyloSynth-555 circuit definition: the single source of truth for schematic, PCB and BOM.

Every part lists {pin_number: net}. A net of None marks an intentionally unconnected pin.
Ladder values come from hardware/design/ladder.json (calc_ladder.py).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

HW = Path(__file__).resolve().parents[1]
LADDER = json.loads((HW / "design" / "ladder.json").read_text())

# ---- footprints -----------------------------------------------------------------------------
FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
FP_R_VERT = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"
FP_C_CER = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_C_FILM = "Capacitor_THT:C_Rect_L7.2mm_W3.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2"
FP_C_FILM_1U = "Capacitor_THT:C_Rect_L7.2mm_W5.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2"
FP_CP5 = "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm"
FP_CP63 = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
FP_CP8 = "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm"
FP_DIP8 = "Package_DIP:DIP-8_W7.62mm_Socket"
FP_DIP16 = "Package_DIP:DIP-16_W7.62mm_Socket"
FP_TO92 = "Package_TO_SOT_THT:TO-92_Inline"
FP_DO41 = "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"
FP_LED = "LED_THT:LED_D3.0mm"
FP_POT = "Potentiometer_THT:Potentiometer_Alps_RK09K_Single_Vertical"
FP_TRIM = "Potentiometer_THT:Potentiometer_Bourns_3296W_Vertical"
FP_SW = "Button_Switch_THT:SW_CK_JS202011CQN_DPDT_Straight"
FP_JACK35 = "Connector_Audio:Jack_3.5mm_CUI_SJ1-3535NG_Horizontal"
FP_BARREL = "Connector_BarrelJack:BarrelJack_CUI_PJ-102AH_Horizontal"
FP_XH2 = "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"
FP_KEYPAD = "StyloSynth:KEYPAD_20"
FP_HOLE = "MountingHole:MountingHole_3.2mm_M3"


@dataclass
class Part:
    ref: str
    lib_id: str
    value: str
    footprint: str
    pins: dict
    block: str
    desc: str = ""
    mpn: str = ""
    fields: dict = field(default_factory=dict)


PARTS: list[Part] = []


def fmt_ohm(r):
    s = f"{r / 1e3:g}k" if r >= 1e3 else f"{r:g}"
    return s.replace(".", "k")[:-1] if "." in s and s.endswith("k") else s


def add(ref, lib_id, value, footprint, pins, block, desc="", mpn=""):
    PARTS.append(Part(ref, lib_id, value, footprint, {str(k): v for k, v in pins.items()}, block, desc, mpn))


def R(ref, value, a, b, block, fp=FP_R, desc="Resistor, metal film 1% 0.25W"):
    add(ref, "Device:R", value, fp, {1: a, 2: b}, block, desc)


def C(ref, value, a, b, block, fp=FP_C_CER, desc="Capacitor, ceramic X7R 50V"):
    add(ref, "Device:C", value, fp, {1: a, 2: b}, block, desc)


def CP(ref, value, pos, neg, block, fp=FP_CP5, desc="Capacitor, aluminium electrolytic 25V"):
    add(ref, "Device:C_Polarized", value, fp, {1: pos, 2: neg}, block, desc)


def DPDT(ref, value, p1, p2, p3, p4, p5, p6, block, desc="Slide switch DPDT, C&K JS202011CQN"):
    add(ref, "Switch:SW_DPDT_x2", value, FP_SW, {1: p1, 2: p2, 3: p3, 4: p4, 5: p5, 6: p6}, block, desc,
        "JS202011CQN")


# ---- power ----------------------------------------------------------------------------------
B = "Power"
add("J1", "Connector:Barrel_Jack_Switch", "9V DC (centre -)", FP_BARREL,
    {1: "GND", 2: "DC_IN", 3: "BAT_P"}, B, "DC barrel jack 2.1mm with switch, CUI PJ-102AH", "PJ-102AH")
add("J2", "Connector_Generic:Conn_01x02", "9V BATT", FP_XH2, {1: "BAT_P", 2: "GND"}, B,
    "JST XH 2-pin header (9V battery snap)", "B2B-XH-A")
add("D1", "Device:D_Schottky", "1N5819", FP_DO41, {1: "VSW_IN", 2: "DC_IN"}, B,
    "Schottky diode 40V 1A (reverse-polarity protection)", "1N5819")
DPDT("SW1", "POWER", "+9V", "VSW_IN", None, "+9V", "VSW_IN", None, B)
CP("C1", "220u", "+9V", "GND", B, FP_CP8, "Capacitor, electrolytic 220uF 16V")
C("C2", "100n", "+9V", "GND", B)
R("R1", "4k7", "+9V", "LED_A", B)
add("D2", "Device:LED", "PWR", FP_LED, {1: "GND", 2: "LED_A"}, B, "LED 3mm red, diffused")
R("R2", "47", "+9V", "V_FILT", B)
CP("C3", "100u", "V_FILT", "GND", B, FP_CP63, "Capacitor, electrolytic 100uF 16V")
add("U1", "Regulator_Linear:LP2950-5.0_TO92", "LP2950-5.0", FP_TO92,
    {1: "+5V", 2: "GND", 3: "V_FILT"}, B, "LDO 5V 100mA, TO-92", "LP2950ACZ-5.0")
CP("C4", "10u", "+5V", "GND", B, FP_CP5, "Capacitor, electrolytic 10uF 25V")
C("C5", "100n", "+5V", "GND", B)

# ---- oscillator -----------------------------------------------------------------------------
B = "Oscillator"
add("U2", "Timer:TLC555xP", "TLC555", FP_DIP8,
    {1: "GND", 2: "TH", 3: "OSC_OUT", 4: "+5V", 5: "CV", 6: "TH", 7: None, 8: "+5V"}, B,
    "CMOS 555 timer, DIP-8 (do not substitute NE555)", "TLC555CP")
C("C6", "100n", "+5V", "GND", B)
C("C7", "22n", "TH", "GND", B, FP_C_FILM, "Capacitor, polypropylene film 22nF 2.5% 100V (timing)")
R("R3", "10M", "TH", "GND", B)
R("R4", "1k5", "+5V", "CV", B)
R("R5", fmt_ohm(LADDER["cv_r_bot_fixed_ohm"]), "CV", "CV_LO", B)
add("RV5", "Device:R_Potentiometer_Trim", fmt_ohm(LADDER["span_trimmer_ohm"]), FP_TRIM,
    {1: "CV_LO", 2: "GND", 3: "GND"}, B, "Trimmer 25-turn, Bourns 3296W (SPAN calibration)", "3296W-1-102LF")
C("C8", "10n", "CV", "GND", B)
R("R6", "100", "STYLUS", "TH", B)
add("J3", "Connector_Audio:AudioJack3_SwitchTR", "STYLUS", FP_JACK35,
    {"T": "STYLUS", "TN": None, "R": None, "RN": None, "S": "GND"}, B,
    "3.5mm TRS jack horizontal, switched, CUI SJ1-3535NG", "SJ1-3535NG")

# ---- key ladder -----------------------------------------------------------------------------
B = "Keys"
prev = "OSC_OUT"
for seg in LADDER["segments"]:
    i, key = seg["segment"], seg["key"]
    node = f"KEY{key}"
    if i == 0:
        R("R101", seg["r_fixed"], prev, "LAD0", B, FP_R_VERT)
        add("RV4", "Device:R_Potentiometer_Trim", fmt_ohm(LADDER["tune_trimmer_ohm"]), FP_TRIM,
            {1: "LAD0", 2: node, 3: node}, B, "Trimmer 25-turn, Bourns 3296W (TUNE calibration)", "3296W-1-202LF")
    else:
        R(f"R{101 + i}", seg["r_fixed"], prev, node, B, FP_R_VERT)
    prev = node
add("K1", "Connector_Generic:Conn_01x20", "KEYPAD", FP_KEYPAD,
    {k: f"KEY{k}" for k in range(1, 21)}, B, "20 exposed ENIG key pads (PCB feature, not a part)")

# ---- octave divider -------------------------------------------------------------------------
B = "Octave"
add("U3", "4xxx:4040", "CD4040", FP_DIP16,
    {1: None, 2: None, 3: None, 4: None, 5: "OCT_Q3", 6: "OCT_Q2", 7: "OCT_Q1", 8: "GND",
     9: "OCT_Q0", 10: "OSC_OUT", 11: "GND", 12: None, 13: None, 14: None, 15: None, 16: "+5V"}, B,
    "12-stage binary counter, DIP-16", "CD4040BE")
C("C9", "100n", "+5V", "GND", B)
DPDT("SW2", "OCT -1", "OCT_Q0", "OCT_M1", "OCT_Q1", "OCT_Q2", "OCT_M2", "OCT_Q3", B)
DPDT("SW3", "OCT -2", "OCT_M1", "OCT_SEL", "OCT_M2", None, None, None, B)

# ---- audio path / amp -----------------------------------------------------------------------
B = "Amp"
R("R7", "150k", "OCT_SEL", "TONE", B)
C("C10", "47n", "TONE", "TONE_SW", B, FP_C_FILM, "Capacitor, polyester film 47nF 63V")
DPDT("SW4", "TONE", "GND", "TONE_SW", None, None, None, None, B)
C("C11", "100n", "TONE", "VOL_TOP", B, FP_C_FILM, "Capacitor, polyester film 100nF 63V")
add("RV1", "Device:R_Potentiometer", "A10k", FP_POT, {1: "GND", 2: "AMP_IN", 3: "VOL_TOP"}, B,
    "Potentiometer 9mm vertical, 10k log, Alps RK09K", "RK09K1130A5R")
add("U4", "Amplifier_Audio:LM386", "LM386", FP_DIP8,
    {1: None, 2: "GND", 3: "AMP_IN", 4: "GND", 5: "AMP_OUT", 6: "+9V", 7: "BYP", 8: None}, B,
    "Audio power amplifier, DIP-8", "LM386N-1")
CP("C12", "10u", "BYP", "GND", B)
CP("C13", "100u", "+9V", "GND", B, FP_CP63, "Capacitor, electrolytic 100uF 16V")
C("C14", "100n", "+9V", "GND", B)
R("R8", "10", "AMP_OUT", "ZOBEL", B)
C("C15", "47n", "ZOBEL", "GND", B)
CP("C16", "220u", "AMP_OUT", "SPK_DRV", B, FP_CP8, "Capacitor, electrolytic 220uF 16V")
R("R9", "220", "SPK_DRV", "HP", B)
# No plug: RN-R and T-TN are closed, so SPK_DRV reaches the speaker directly.
# Plug in: speaker is disconnected and the headphones get SPK_DRV through R9.
add("J4", "Connector_Audio:AudioJack3_SwitchTR", "PHONES", FP_JACK35,
    {"T": "HP", "TN": "SPK_P", "R": "HP", "RN": "SPK_DRV", "S": "GND"}, B,
    "3.5mm TRS jack horizontal, switched, CUI SJ1-3535NG", "SJ1-3535NG")
add("J5", "Connector_Generic:Conn_01x02", "SPEAKER", FP_XH2, {1: "SPK_P", 2: "GND"}, B,
    "JST XH 2-pin header (speaker)", "B2B-XH-A")

# ---- vibrato LFO ----------------------------------------------------------------------------
B = "Vibrato"
add("U5", "Amplifier_Operational:LM358", "LM358", FP_DIP8,
    {1: "LFO_SQ", 2: "LFO_C", 3: "LFO_P", 4: "GND", 5: "LFO_C", 6: "LFO_BUF", 7: "LFO_BUF", 8: "+5V"}, B,
    "Dual op-amp, DIP-8", "LM358P")
C("C17", "100n", "+5V", "GND", B)
R("R10", "100k", "+5V", "LFO_P", B)
R("R11", "100k", "LFO_P", "GND", B)
R("R12", "100k", "LFO_SQ", "LFO_P", B)
R("R13", "68k", "LFO_SQ", "LFO_R", B)
add("RV2", "Device:R_Potentiometer_Trim", "100k", FP_TRIM, {1: "LFO_R", 2: "LFO_C", 3: "LFO_C"}, B,
    "Trimmer 25-turn, Bourns 3296W (vibrato rate)", "3296W-1-104")
C("C18", "1u", "LFO_C", "GND", B, FP_C_FILM_1U, "Capacitor, polyester film 1uF 63V")
CP("C19", "22u", "LFO_BUF", "DEPTH_TOP", B)
add("RV3", "Device:R_Potentiometer", "B10k", FP_POT, {1: "GND", 2: "DEPTH_W", 3: "DEPTH_TOP"}, B,
    "Potentiometer 9mm vertical, 10k linear, Alps RK09K", "RK09K1130A8G")
DPDT("SW5", "VIBRATO", "GND", "DEPTH_W", None, None, None, None, B)
R("R14", "4k7", "DEPTH_W", "VIB_INJ", B)
CP("C20", "47u", "CV", "VIB_INJ", B)

# ---- mechanical -----------------------------------------------------------------------------
for n in range(1, 7):
    add(f"H{n}", "Mechanical:MountingHole", "M3", FP_HOLE, {}, "Mechanical", "Mounting hole M3")

# nets that need a PWR_FLAG for ERC (driven only through passive parts)
PWR_FLAG_NETS = ["GND", "+9V", "V_FILT"]


def nets():
    out = {}
    for p in PARTS:
        for pin, net in p.pins.items():
            if net is not None:
                out.setdefault(net, []).append((p.ref, pin))
    return out


if __name__ == "__main__":
    n = nets()
    single = {k: v for k, v in n.items() if len(v) < 2}
    print(f"{len(PARTS)} parts, {len(n)} nets")
    if single:
        raise SystemExit(f"nets with a single connection: {single}")
    print("all nets have >= 2 connections")
